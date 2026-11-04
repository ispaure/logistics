"""A float Cocoa OpenGL surface for libmpv, composited with existing Qt chrome."""
import ctypes as C
from commonUtils.ui import pyside as qt
from .mpv_binding import GET_PROC, UPDATE, GLInit, RenderParam, Fbo


class CocoaGL:
    """Typed Objective-C calls owned by this view, without a second GUI toolkit."""
    def __init__(self):
        self.objc = C.CDLL('/usr/lib/libobjc.A.dylib')
        self.objc.sel_registerName.argtypes, self.objc.sel_registerName.restype = [C.c_char_p], C.c_void_p
        self.objc.objc_getClass.argtypes, self.objc.objc_getClass.restype = [C.c_char_p], C.c_void_p
        self.message = C.cast(self.objc.objc_msgSend, C.c_void_p).value
        self.gl = C.CDLL('/System/Library/Frameworks/OpenGL.framework/OpenGL')
        self.functions = {}
        self.context, self.view, self.window = None, None, None

    def send(self, obj, selector, result=C.c_void_p, args=(), values=()):
        key = (selector, result, args)
        if key not in self.functions:
            self.functions[key] = (C.CFUNCTYPE(result, C.c_void_p, C.c_void_p, *args)(self.message),
                                   self.objc.sel_registerName(selector.encode()))
        function, name = self.functions[key]
        return function(obj, name, *values)

    def create(self, view):
        # Qt's QSurfaceFormat does not request NSOpenGLPFAColorFloat. An explicit
        # float pixel format avoids clipping HDR to an 8-bit default framebuffer.
        attrs = (C.c_uint * 12)(99, 0x3200, 73, 5, 58, 8, 64, 11, 16, 96, 0, 0)
        cls = self.objc.objc_getClass
        pixel = self.send(self.send(cls(b'NSOpenGLPixelFormat'), 'alloc'), 'initWithAttributes:',
                          args=(C.POINTER(C.c_uint),), values=(attrs,))
        if not pixel:
            raise RuntimeError('Floating-point video output is unavailable on this display.')
        try:
            self.context = self.send(self.send(cls(b'NSOpenGLContext'), 'alloc'), 'initWithFormat:shareContext:',
                                     args=(C.c_void_p, C.c_void_p), values=(pixel, None))
        finally:
            self.send(pixel, 'release', None)
        if not self.context:
            raise RuntimeError('The colour video surface could not initialize.')
        self.bind(view)

    def bind(self, view):
        changed = self.view != view
        if changed:
            self.send(self.context, 'setView:', None, (C.c_void_p,), (view,))
            self.view = view
        window = self.send(view, 'window')
        if window and window != self.window:
            # Extended sRGB keeps Qt's ordinary sRGB controls unchanged while
            # permitting the float OpenGL surface to carry values above white.
            space = self.send(self.objc.objc_getClass(b'NSColorSpace'), 'extendedSRGBColorSpace')
            self.send(window, 'setColorSpace:', None, (C.c_void_p,), (space,))
            self.window = window
        if changed:
            self.send(view, 'setWantsBestResolutionOpenGLSurface:', None, (C.c_bool,), (True,))
            self.send(view, 'setWantsExtendedDynamicRangeOpenGLSurface:', None, (C.c_bool,), (True,))
        self.send(self.context, 'makeCurrentContext', None)
        self.send(self.context, 'update', None)

    def headroom(self):
        screen = self.send(self.send(self.view, 'window'), 'screen')
        value = self.send(screen, 'maximumExtendedDynamicRangeColorComponentValue', C.c_double) if screen else 1
        return max(1., min(100., float(value)))

    def function(self, name, result, args):
        return C.CFUNCTYPE(result, *args)(C.cast(getattr(self.gl, name), C.c_void_p).value)

    def flush(self):
        self.send(self.context, 'flushBuffer', None)

    def close(self):
        if self.context:
            self.send(self.context, 'clearDrawable', None)
            self.send(self.context, 'release', None)
            self.context = None


class PresentedFrame:
    def __init__(self, surface):
        self.surface = surface

    def isValid(self):
        return self.surface.have_frame

    def toImage(self):
        return self.surface.capture() if self.isValid() else qt.QImage()


class ColourSink(qt.QObject):
    videoFrameChanged = qt.Signal(object)
    videoSizeChanged = qt.Signal(qt.QSize)

    def __init__(self, surface):
        super().__init__(surface)
        self.surface, self.size = surface, qt.QSize()

    def videoSize(self):
        return self.size

    def set_size(self, size):
        if size != self.size:
            self.size = size
            self.videoSizeChanged.emit(size)


class ColourSurface(qt.QWidget):
    wake = qt.Signal()
    ready = qt.Signal()
    submitted = qt.Signal()
    failed = qt.Signal(str)

    def __init__(self, core):
        super().__init__()
        self.core, self.api = core, core.api
        self.native, self.render_context = None, C.c_void_p()
        self.sink = ColourSink(self)
        self.closed = self.source_ready = self.have_frame = False
        self.aspect = qt.Qt.AspectRatioMode.KeepAspectRatio
        self.output_headroom, self.output_mode, self.tone_map = 1., 'auto', 'bt.2390'
        self._output_key = None
        self.red_bits = 0
        self.probe_samples = False
        self.samples = []
        self.get_proc = GET_PROC(self.procedure)
        self.update_callback = UPDATE(self.request_frame)
        self.wake.connect(self.update, qt.Qt.ConnectionType.QueuedConnection)
        core.redraw.connect(self.repaint, qt.Qt.ConnectionType.QueuedConnection)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_NativeWindow)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setAccessibleName('Colour-managed video')

    def videoSink(self):
        return self.sink

    def procedure(self, unused, name):
        try:
            return C.cast(getattr(self.native.gl, name.decode()), C.c_void_p).value
        except AttributeError:
            return None

    def request_frame(self, unused):
        if not self.closed:
            self.wake.emit()

    def initialize(self):
        self.native = CocoaGL()
        self.native.create(int(self.winId()))
        data, name = GLInit(self.get_proc, None), C.create_string_buffer(b'opengl')
        params = (RenderParam * 3)(RenderParam(1, C.addressof(name)),
                                  RenderParam(2, C.addressof(data)), RenderParam(0, None))
        if self.api.render_context_create(C.byref(self.render_context), self.core.handle, params) < 0:
            raise RuntimeError('The colour video renderer could not initialize.')
        self.api.render_context_set_update_callback(self.render_context, self.update_callback, None)
        get = self.native.function('glGetFramebufferAttachmentParameteriv', None,
                                  (C.c_uint, C.c_uint, C.c_uint, C.POINTER(C.c_int)))
        bits = C.c_int()
        get(0x8d40, 0x0402, 0x8212, C.byref(bits))
        self.red_bits = bits.value
        self.configure_output()
        self.ready.emit()

    def configure_output(self, mode=None, tone_map=None):
        if mode is not None:
            self.output_mode = mode
        if tone_map is not None:
            self.tone_map = tone_map
        headroom = self.native.headroom() if self.native and self.red_bits >= 16 and self.output_mode == 'auto' else 1.
        self.output_headroom = headroom
        key = (headroom, self.tone_map)
        if key == self._output_key:
            return
        self._output_key = key
        self.core.submit('set', 'target-trc', 'pq')
        self.core.submit('set', 'target-prim', 'bt.709')
        self.core.submit('set', 'target-peak', round(203 * headroom))
        self.core.submit('set', 'tone-mapping', self.tone_map)
        self.update()

    def setAspectRatioMode(self, mode):
        self.aspect = mode
        self.core.submit('set', 'panscan', 1 if mode == qt.Qt.AspectRatioMode.KeepAspectRatioByExpanding else 0)
        self.update()

    def paintEvent(self, event):
        if self.closed:
            return
        try:
            if self.native is None:
                self.initialize()
            self.native.bind(int(self.winId()))
            width, height = round(self.width() * self.devicePixelRatioF()), round(self.height() * self.devicePixelRatioF())
            if self.source_ready:
                changed = bool(self.api.render_context_update(self.render_context) & 1)
                fbo, flip, depth = Fbo(0, width, height, 0x881a), C.c_int(1), C.c_int(self.red_bits)
                params = (RenderParam * 4)(RenderParam(3, C.addressof(fbo)),
                                          RenderParam(4, C.addressof(flip)), RenderParam(5, C.addressof(depth)),
                                          RenderParam(0, None))
                if self.api.render_context_render(self.render_context, params) < 0:
                    raise RuntimeError('The colour video frame could not be presented.')
                self.have_frame = self.have_frame or changed
                if self.probe_samples:
                    self.samples = self.sample_pixels(width, height)
                if changed:
                    self.sink.videoFrameChanged.emit(PresentedFrame(self))
                    self.submitted.emit()
            else:
                self.native.function('glClearColor', None, (C.c_float,) * 4)(0, 0, 0, 1)
                self.native.function('glClear', None, (C.c_uint,))(0x4000)
            self.native.flush()
            if self.source_ready:
                self.api.render_context_report_swap(self.render_context)
        except (RuntimeError, OSError) as error:
            self.failed.emit(str(error))

    def sample_pixels(self, width, height):
        read = self.native.function('glReadPixels', None,
                                   (C.c_int, C.c_int, C.c_int, C.c_int, C.c_uint, C.c_uint, C.c_void_p))
        values = []
        for index in range(8):
            pixel = (C.c_float * 4)()
            read(round(width * (index + .5) / 8), height // 2, 1, 1, 0x1908, 0x1406, pixel)
            values.append(list(pixel))
        return values

    def capture(self):
        if not self.native or self.closed:
            return qt.QImage()
        self.native.bind(int(self.winId()))
        width, height = round(self.width() * self.devicePixelRatioF()), round(self.height() * self.devicePixelRatioF())
        pixels = (C.c_ubyte * (width * height * 4))()
        self.native.function('glReadPixels', None, (C.c_int,) * 4 + (C.c_uint, C.c_uint, C.c_void_p))(
            0, 0, width, height, 0x1908, 0x1401, pixels)
        image = qt.QImage(bytes(pixels), width, height, width * 4, qt.QImage.Format.Format_RGBA8888).copy().flipped()
        image.setColorSpace(qt.QColorSpace(qt.QColorSpace.NamedColorSpace.SRgb))
        return image

    def clear(self):
        self.source_ready = self.have_frame = False
        self.sink.videoFrameChanged.emit(PresentedFrame(self))
        self.update()

    def retire(self):
        if self.closed:
            return
        self.closed = True
        if self.native:
            self.native.bind(int(self.winId()))
            if self.render_context.value:
                self.api.render_context_set_update_callback(self.render_context, UPDATE(), None)
                self.api.render_context_free(self.render_context)
                self.render_context = C.c_void_p()
            self.native.close()
        self.have_frame = False
