"""EPUB contents float above the retained page on phones and wide readers."""
from types import SimpleNamespace
import toga
from toga.style import Pack
from commonUtils.ui.native.presentation import sidebar_button
from .speech_overlay import SpeechOverlay


class ChapterDrawer:
    # Retain the reader host's sidebar contract without reserving page width.
    expanded = False

    def __init__(self, sidebar, detail, *, app, label='Browse book chapters'):
        self.app, self.sidebar, self.detail = app, sidebar, detail
        self.policy = SimpleNamespace(sidebar_width=0, gap=0)
        self.sidebar_open = False
        self.overlay = None
        self.view = toga.Box(children=[detail], style=Pack(flex=1))
        self.menu_button = sidebar_button(self.toggle, label)
        sidebar.hide = self.show_detail
        sidebar.overlay = None
        sidebar.overlay_height = 480  # Native drawer measures its window height.

    def reflow(self, width):
        if self.overlay is not None:
            self.overlay.reposition()
        return False

    def toggle(self, widget=None, **kwargs):
        if self.sidebar_open:
            self.show_detail()
        else:
            self.show_sidebar()

    def show_sidebar(self):
        if self.overlay is not None:
            return
        self.sidebar_open = True
        self.overlay = SpeechOverlay(self.sidebar, self.view, self.app,
                                     anchor=self.menu_button, leading=True)
        self.overlay.chapter_owner = self.view
        self.sidebar.overlay = self.overlay
        if self.app.preferences.values.get('android_eink') != 'true':
            from commonUtils.ui.native.transitions import begin_page_slide, finish_page_slide
            begin_page_slide(self.sidebar, -1)
            finish_page_slide(self.sidebar, -1)

    def show_detail(self):
        self.sidebar_open = False
        overlay, self.overlay = self.overlay, None
        self.sidebar.overlay = None
        self.cancel_motion()
        if overlay is not None:
            overlay.close()

    def cancel_motion(self):
        impl = self.sidebar._impl
        backend = type(impl).__module__
        if backend.startswith('toga_iOS.'):
            impl.native.layer.removeAnimationForKey('commonutils.page')
        elif backend.startswith('toga_android.'):
            impl.native.clearAnimation()
