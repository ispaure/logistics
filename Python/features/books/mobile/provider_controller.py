"""Feature-owned reader workflow state and explicit host dependencies."""

from services.workflow_host import HostAttribute


class ProviderBookController:
    METHODS = (
        "show_provider_epub_find",
        "toggle_provider_epub_tools",
        "show_provider_epub_navigation",
        "open_provider_epub_chapter",
        "watch_provider_epub_width",
        "show_provider_read_aloud",
    )
    FIELDS = (
        "provider_epub_view",
        "_provider_epub_target",
        "_provider_width_task",
        "_provider_width_panel",
    )
    page_suspended = HostAttribute("page_suspended")
    cloud_busy = HostAttribute("cloud_busy")
    crypt_content = HostAttribute("crypt_content")
    crypt_immersive = HostAttribute("crypt_immersive")
    crypt_reader = HostAttribute("crypt_reader")
    format_services = HostAttribute("format_services")
    loop = HostAttribute("loop")
    main_window = HostAttribute("main_window")
    move_private_page = HostAttribute("move_private_page")
    privacy_gate = HostAttribute("privacy_gate")
    read_crypt_page = HostAttribute("read_crypt_page")
    resume_crypt = HostAttribute("resume_crypt")

    def __init__(self, owner):
        self.app = owner

    def show_provider_epub_find(self, widget=None, **kwargs):
        panel = getattr(self, "provider_epub_view", None)
        if panel is not None and not self.cloud_busy:
            if hasattr(panel, "show_find"):
                panel.show_find()
            else:
                panel.tools.toggle()

    def toggle_provider_epub_tools(self, widget=None, **kwargs):
        panel = getattr(self, "provider_epub_view", None)
        if not self.cloud_busy and panel is not None:
            panel.tools.toggle()

    async def show_provider_epub_navigation(self, widget=None, **kwargs):
        if (
            self.cloud_busy
            or self.crypt_reader is None
            or self.crypt_reader.book is None
        ):
            return
        if getattr(self, "page_suspended", False):
            await self.read_crypt_page()
        self.resume_crypt()
        panel = getattr(self, "provider_epub_view", None)
        if panel is not None and panel.tools.panel not in panel.tools.widget.children:
            panel.tools.toggle()

    def open_provider_epub_chapter(self, index, fragment=""):
        if self.cloud_busy or self.crypt_reader is None:
            return
        self._provider_epub_target = fragment
        self.loop.create_task(self.move_private_page(index))

    def watch_provider_epub_width(self):
        task = getattr(self, "_provider_width_task", None)
        if not hasattr(self, "provider_epub_view"):
            return
        panel = self.provider_epub_view
        if task is not None and not task.done():
            if getattr(self, "_provider_width_panel", None) is panel:
                return
            task.cancel()
        self._provider_width_panel = panel
        from features.books.mobile.presentation import watch_width, pane_width

        def width():
            available = pane_width(self.crypt_content, self.main_window.size.width, 0)
            if hasattr(panel, "reflow"):
                panel.reflow(available, immersive=self.crypt_immersive)
            return available

        self._provider_width_task = self.loop.create_task(
            watch_width(
                alive=lambda: getattr(self, "provider_epub_view", None) is panel,
                width=width,
                view=lambda: panel,
                changed=self.format_services.layout_changed(),
            )
        )

    def show_provider_read_aloud(self, widget=None, **kwargs):
        panel = getattr(self, "provider_epub_view", None)
        if (
            panel is not None
            and hasattr(panel, "show_read_aloud")
            and not self.cloud_busy
        ):
            panel.show_read_aloud(
                self.loop,
                presentation=self.format_services.speech_presentation,
                highlight_allowed=self.format_services.highlight_allowed,
                privacy_gate=lambda: self.privacy_gate,
                valid=lambda: self.format_services.speech_valid(),
            )
