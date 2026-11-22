"""Small libmpv ABI and serialized worker; no native calls in renderer callbacks."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import ctypes as C
from queue import Empty, Queue
from threading import Thread
from time import monotonic
from commonUtils.ui import pyside as qt


class Node(C.Structure):
    pass


class NodeList(C.Structure):
    _fields_ = [('num', C.c_int), ('values', C.POINTER(Node)), ('keys', C.POINTER(C.c_char_p))]


class Value(C.Union):
    _fields_ = [('string', C.c_char_p), ('flag', C.c_int), ('integer', C.c_int64),
                ('number', C.c_double), ('list', C.POINTER(NodeList))]


Node._fields_ = [('u', Value), ('format', C.c_int)]


class Event(C.Structure):
    _fields_ = [('id', C.c_int), ('error', C.c_int), ('userdata', C.c_uint64), ('data', C.c_void_p)]


GET_PROC = C.CFUNCTYPE(C.c_void_p, C.c_void_p, C.c_char_p)
UPDATE = C.CFUNCTYPE(None, C.c_void_p)


class GLInit(C.Structure):
    _fields_ = [('get_proc_address', GET_PROC), ('context', C.c_void_p)]


class RenderParam(C.Structure):
    _fields_ = [('type', C.c_int), ('data', C.c_void_p)]


class Fbo(C.Structure):
    _fields_ = [('id', C.c_int), ('width', C.c_int), ('height', C.c_int), ('format', C.c_int)]


def node_value(node, depth=0):
    if depth > 12:
        raise ValueError('Excessive decoder metadata nesting.')
    if node.format == 1:
        return (node.u.string or b'').decode('utf-8', 'replace')
    if node.format == 3:
        return bool(node.u.flag)
    if node.format == 4:
        return int(node.u.integer)
    if node.format == 5:
        return float(node.u.number)
    if node.format in (7, 8) and node.u.list:
        rows = node.u.list.contents
        if not 0 <= rows.num <= 10000:
            raise ValueError('Excessive decoder metadata.')
        values = [node_value(rows.values[i], depth + 1) for i in range(rows.num)]
        return values if node.format == 7 else dict(zip(
            [(rows.keys[i] or b'').decode('utf-8', 'replace') for i in range(rows.num)], values))
    return None


class API:
    def __init__(self, library):
        self.library = library
        signatures = {
            'create': (C.c_void_p, []), 'initialize': (C.c_int, [C.c_void_p]),
            'set_option_string': (C.c_int, [C.c_void_p, C.c_char_p, C.c_char_p]),
            'set_property_string': (C.c_int, [C.c_void_p, C.c_char_p, C.c_char_p]),
            'get_property': (C.c_int, [C.c_void_p, C.c_char_p, C.c_int, C.c_void_p]),
            'free_node_contents': (None, [C.POINTER(Node)]),
            'command': (C.c_int, [C.c_void_p, C.POINTER(C.c_char_p)]),
            'wait_event': (C.POINTER(Event), [C.c_void_p, C.c_double]),
            'terminate_destroy': (None, [C.c_void_p]),
            'render_context_create': (C.c_int, [C.POINTER(C.c_void_p), C.c_void_p, C.POINTER(RenderParam)]),
            'render_context_render': (C.c_int, [C.c_void_p, C.POINTER(RenderParam)]),
            'render_context_update': (C.c_uint64, [C.c_void_p]),
            'render_context_set_update_callback': (None, [C.c_void_p, UPDATE, C.c_void_p]),
            'render_context_report_swap': (None, [C.c_void_p]),
            'render_context_free': (None, [C.c_void_p]),
        }
        for name, (result, args) in signatures.items():
            function = getattr(library, 'mpv_' + name)
            function.restype, function.argtypes = result, args
            setattr(self, name, function)

    def command_args(self, handle, *args):
        encoded = [str(arg).encode() for arg in args]
        return self.command(handle, (C.c_char_p * (len(encoded) + 1))(*encoded, None))

    def property(self, handle, name):
        node = Node()
        if self.get_property(handle, name.encode(), 6, C.byref(node)) < 0:
            return None
        try:
            return node_value(node)
        finally:
            self.free_node_contents(C.byref(node))


class Core(qt.QObject):
    snapshot = qt.Signal(object)
    redraw = qt.Signal()

    def __init__(self, api, options, parent):
        super().__init__(parent)
        self.api, self.handle = api, api.create()
        self.queue, self.closed = Queue(), False
        if not self.handle:
            raise RuntimeError('The colour video decoder could not initialize.')
        try:
            for key, value in options.items():
                if api.set_option_string(self.handle, key.encode(), str(value).encode()) < 0:
                    raise ValueError('Unsupported colour video option: ' + key)
            if api.initialize(self.handle) < 0:
                raise RuntimeError('The colour video decoder could not initialize.')
        except BaseException:
            api.terminate_destroy(self.handle)
            raise
        self.thread = Thread(target=self.run, name='colour-video', daemon=True)
        self.thread.start()

    def submit(self, *command):
        if not self.closed:
            self.queue.put(command)

    def pause(self, paused):
        self.api.set_property_string(self.handle, b'pause', b'yes' if paused else b'no')

    def switch_audio(self, track, position):
        # Hold the native clock while changing the audio chain and requesting
        # A/V preroll. The seek event releases this hold if Play is intended.
        self.pause(True)
        return (self.api.property(self.handle, 'seekable')
            and self.api.set_property_string(self.handle, b'aid', str(track).encode()) >= 0
            and self.api.command_args(self.handle, 'seek', position / 1000, 'absolute+exact') >= 0)

    def run(self):
        generation, loaded, desired_pause, pending_seek, failed = 0, False, True, None, False
        switch_serial, switch_state = None, None
        last = 0
        try:
            while True:
                try:
                    command = self.queue.get_nowait()
                except Empty:
                    command = ()
                if command:
                    kind, *args = command
                    if kind == 'retire':
                        return
                    if kind == 'source':
                        generation, url = args
                        loaded, pending_seek, failed = False, None, False
                        switch_serial, switch_state = None, None
                        self.api.command_args(self.handle, 'stop')
                        self.pause(True)
                        if url:
                            self.api.command_args(self.handle, 'loadfile', url)
                    elif kind == 'pause':
                        desired_pause = args[0]
                        if switch_state != 'awaiting-seek':
                            self.pause(desired_pause)
                    elif kind == 'seek':
                        pending_seek = args[0]
                        if loaded:
                            self.api.command_args(self.handle, 'seek', pending_seek / 1000, 'absolute+exact')
                            pending_seek = None
                    elif kind == 'switch-audio':
                        switch_serial, track, position = args
                        switch_state = 'awaiting-seek' if loaded and self.switch_audio(track, position) else 'failed'
                    elif kind == 'clear-audio-switch':
                        if switch_serial == args[0]:
                            switch_serial, switch_state = None, None
                    elif kind == 'set':
                        result = self.api.set_property_string(self.handle, str(args[0]).encode(), str(args[1]).encode())
                        if args[0] in {'target-trc', 'target-prim', 'target-peak', 'tone-mapping'}:
                            if result < 0:
                                raise RuntimeError('The colour output configuration was rejected.')
                            self.redraw.emit()
                        elif args[0] == 'sub-color' and result >= 0:
                            self.redraw.emit()
                    elif kind == 'command':
                        if args[0] == 'stop':
                            switch_serial, switch_state = None, None
                        self.api.command_args(self.handle, *args)
                    continue
                event = self.api.wait_event(self.handle, .02).contents
                if event.id == 8:
                    loaded = True
                    if pending_seek is not None:
                        self.api.command_args(self.handle, 'seek', pending_seek / 1000, 'absolute+exact')
                        pending_seek = None
                    self.pause(desired_pause)
                if event.id == 7:
                    loaded = False
                    if event.data:
                        failed = C.cast(event.data, C.POINTER(C.c_int))[0] == 4
                if event.id == 20 and switch_state == 'awaiting-seek':  # MPV_EVENT_SEEK
                    switch_state = 'seeking'
                    self.pause(desired_pause)
                if event.id == 21 and switch_state == 'seeking':  # MPV_EVENT_PLAYBACK_RESTART
                    switch_state = 'restarted'
                now = monotonic()
                if now - last >= .1:
                    keys = ('time-pos', 'duration', 'pause', 'eof-reached', 'seeking', 'paused-for-cache',
                            'video-out-params', 'video-params', 'track-list', 'chapter-list', 'target-peak', 'target-trc',
                            'audio-pts')
                    state = {key: self.api.property(self.handle, key) for key in keys}
                    state.update(generation=generation, loaded=loaded, error=failed)
                    if switch_serial is not None:
                        state['audio-switch'] = (switch_serial, switch_state)
                    if not self.closed:
                        self.snapshot.emit(state)
                    last = now
        except Exception:
            if not self.closed:
                self.snapshot.emit(dict(generation=generation, loaded=False, error=True))
            # Keep the core alive until the UI releases its render context.
            # Destroying it underneath that context would violate libmpv's ABI.
            while self.queue.get()[0] != 'retire':
                pass
        finally:
            self.api.terminate_destroy(self.handle)

    def retire(self):
        if not self.closed:
            self.closed = True
            self.queue.put(('retire',))
            self.thread.join()
