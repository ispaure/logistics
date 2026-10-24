"""Feature-owned reader workflow state and explicit host dependencies."""

import asyncio
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from features.books.locations import link_destination
from services.workflow_host import HostAttribute
from .content import indexed_chapter
from .typography import options as typography_options


class EpubController:
    METHODS = (
        "epub_event",
        "request_position_flush",
        "save_epub_location",
        "epub_boundary",
        "epub_link",
        "show_epub_search",
        "find_epub_next",
        "watch_epub_width",
    )
    FIELDS = (
        "epub_text",
        "epub_offset",
        "epub_view",
        "epub_query",
        "epub_search_status",
        "_epub_target",
        "_epub_pending",
        "_epub_flush",
        "_epub_location_task",
        "_epub_width_task",
    )
    preferences = HostAttribute("preferences")
    _book_idle = HostAttribute("_book_idle")
    active_host = HostAttribute("active_host")
    book_busy = HostAttribute("book_busy")
    book_epoch = HostAttribute("book_epoch")
    book_reader = HostAttribute("book_reader")
    book_record = HostAttribute("book_record")
    book_status = HostAttribute("book_status")
    chapter_sidebar = HostAttribute("chapter_sidebar")
    format_services = HostAttribute("format_services")
    library_store = HostAttribute("library_store")
    library_view = HostAttribute("library_view")
    loop = HostAttribute("loop")
    manager = HostAttribute("manager")
    move_book_page = HostAttribute("move_book_page")
    page_footer = HostAttribute("page_footer")
    presentation_destination = HostAttribute("presentation_destination")
    reflow_chapters = HostAttribute("reflow_chapters")
    session = HostAttribute("session")
    set_book_busy = HostAttribute("set_book_busy")
    show_library = HostAttribute("show_library")
    show_view = HostAttribute("show_view")
    workspace = HostAttribute("workspace")

    def __init__(self, owner):
        self.app = owner

    def epub_event(self, reader, epoch, index, action, offset):
        if (
            self.book_reader is not reader
            or self.book_epoch != epoch
            or not self.active_host
            or self.session.id not in self.workspace.sessions
        ):
            return
        self.epub_offset = min(offset, self.epub_text.length)
        if hasattr(self, "page_footer"):
            self.page_footer.chapter_progress(
                index, len(reader.spine), self.epub_offset, self.epub_text.length
            )
        self._epub_pending = (reader, epoch, index, self.epub_offset)
        task = getattr(self, "_epub_location_task", None)
        if task is None or task.done():
            self._epub_flush = asyncio.Event()
            self._epub_location_task = self.loop.create_task(self.save_epub_location())
        if action in {"next", "previous"} and not self.book_busy:
            self.loop.create_task(
                self.epub_boundary(index, 1 if action == "next" else -1)
            )

    def request_position_flush(self):
        wake = getattr(self, "_epub_flush", None)
        if wake is not None:
            wake.set()

    async def save_epub_location(self):
        # A fixed window bounds latency even while position events keep arriving.
        try:
            await asyncio.wait_for(self._epub_flush.wait(), 0.15)
        except asyncio.TimeoutError:
            pass
        while getattr(self, "_epub_pending", None) is not None:
            if self.book_busy:
                await self._book_idle.wait()
                continue
            reader, epoch, index, offset = self._epub_pending
            self._epub_pending = None
            if (
                self.book_reader is not reader
                or self.book_epoch != epoch
                or self.book_record["position"] != index
            ):
                continue
            self.set_book_busy(True)
            try:
                updated = await asyncio.to_thread(
                    self.library_store.progress,
                    self.book_record,
                    index,
                    location=dict(path=reader.spine[index], offset=offset),
                )
                if self.book_reader is reader and self.book_epoch == epoch:
                    self.book_record = updated
            except (OSError, ValueError) as error:
                self.book_status.text = (
                    "Cannot save reading position: " + str(error)[:300]
                )
            finally:
                self.set_book_busy(False)

    async def epub_boundary(self, index, direction):
        task = getattr(self, "_epub_location_task", None)
        if task is not None:
            self.request_position_flush()
            await task
        if self.book_reader is not None and self.book_record["position"] == index:
            target = index + direction
            if 0 <= target < len(self.book_reader.spine):
                self._epub_target = 0 if direction > 0 else 16 * 1024 * 1024
                await self.move_book_page(target)

    def epub_link(self, reader, epoch, index, href):
        if (
            self.book_reader is not reader
            or self.book_epoch != epoch
            or self.book_busy
            or self.manager.active is not self.app
            or not self.active_host
        ):
            return
        try:
            target, fragment = link_destination(reader, index, href)
            self._epub_target = fragment
            self.loop.create_task(self.move_book_page(target))
        except ValueError as error:
            self.book_status.text = str(error)

    def show_epub_search(self, widget=None, **kwargs):
        if self.book_reader is None or self.book_record["kind"] != "epub":
            return
        self.epub_query = toga.TextInput(
            placeholder="Find in this chapter…",
            on_confirm=self.find_epub_next,
            style=Pack(height=44),
        )
        self.epub_search_status = toga.Label(
            "Search ignores case and wraps\nwithin this chapter."
        )
        view = toga.Box(
            children=[
                self.epub_query,
                toga.Button(
                    "Find next", on_press=self.find_epub_next, style=Pack(height=44)
                ),
                self.epub_search_status,
                toga.Button(
                    "Return to reading",
                    on_press=self.show_library,
                    style=Pack(height=44),
                ),
            ],
            style=Pack(direction=COLUMN, margin=12),
        )
        self.show_view(view, reader_route="search", title="Find in chapter")

    async def find_epub_next(self, widget=None, **kwargs):
        if (
            self.book_busy
            or self.book_reader is None
            or self.book_record["kind"] != "epub"
        ):
            return
        result = self.epub_text.find(self.epub_query.value, self.epub_offset + 1)
        if result is None:
            self.epub_search_status.text = "No matching text in this chapter."
            return
        start, end = result
        self.epub_offset = start
        self.epub_view._chapter_bridge.seek(start, end)
        self.epub_event(
            self.book_reader,
            self.book_epoch,
            self.book_record["position"],
            "position",
            start,
        )
        self.show_library()

    def watch_epub_width(self, reader, epoch):
        task = getattr(self, "_epub_width_task", None)
        if task is not None and not task.done():
            return
        from features.books.mobile.presentation import watch_width, pane_width

        def width():
            self.reflow_chapters()
            available = pane_width(
                self.library_view,
                self.format_services.content_width(self.presentation_destination),
                0,
            )
            sidebar = self.chapter_sidebar
            return max(
                1,
                available
                - (
                    sidebar.policy.sidebar_width + sidebar.policy.gap
                    if sidebar.expanded
                    else 0
                ),
            )

        self._epub_width_task = self.loop.create_task(
            watch_width(
                alive=lambda: self.book_reader is reader and self.book_epoch == epoch,
                width=width,
                view=lambda: self.epub_view,
                changed=self.format_services.layout_changed(),
            )
        )

    async def prepare_page(self, reader, record, index, epoch):
        async def seek(chapter, fraction):
            self._epub_target = ('fraction', fraction)
            await self.move_book_page(chapter)
        self.page_footer.set_book(reader, seek)
        content, chapter_text = await asyncio.to_thread(
            indexed_chapter,
            reader,
            index,
            int(self.preferences.values["epub_font_size"]),
            margin=int(self.preferences.values["reading_margin"]),
            theme=self.preferences.values["reading_theme"],
            links=True,
            **typography_options(self.preferences.values),
        )

        content = self.format_services.themed_chapter(
            content, self.preferences.values["reading_theme"]
        )
        if (
            epoch != self.book_epoch
            or self.book_reader is not reader
            or not self.active_host
        ):
            return
        target = getattr(self, "_epub_target", None)
        self._epub_target = None
        saved = record.get("location", {})
        offset = (
            saved.get("offset", 0) if saved.get("path") == reader.spine[index] else 0
        )
        if target is not None:
            offset = (round(chapter_text.length * target[1]) if isinstance(target, tuple)
                      else chapter_text.anchors.get(target, 0) if isinstance(target, str) else target)
        offset = min(max(0, offset), chapter_text.length)
        return chapter_text, offset, content
