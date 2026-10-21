"""Feature-owned reader workflow state and explicit host dependencies."""

import asyncio
from services.workflow_host import HostAttribute
from .navigation import ComicNavigation
from .presentation import page_view, SpreadView


class ComicController:
    METHODS = (
        "comic_seam",
        "comic_layout_mode",
        "comic_viewport",
        "move_comic",
        "adjacent_book_comic",
        "previous_comic_file",
        "next_comic_file",
        "watch_comic_layout",
        "first_comic_page",
        "last_comic_page",
    )
    FIELDS = (
        "comic_navigation",
        "_comic_navigation_reader",
        "_comic_layout_task",
        "_comic_mode_started",
    )
    swipe_book_page = HostAttribute("swipe_book_page")
    toggle_reading_mode = HostAttribute("toggle_reading_mode")
    active_host = HostAttribute("active_host")
    book_busy = HostAttribute("book_busy")
    book_content = HostAttribute("book_content")
    book_epoch = HostAttribute("book_epoch")
    book_reader = HostAttribute("book_reader")
    book_record = HostAttribute("book_record")
    book_status = HostAttribute("book_status")
    preferences = HostAttribute("preferences")
    format_services = HostAttribute("format_services")
    library_store = HostAttribute("library_store")
    loop = HostAttribute("loop")
    main_window = HostAttribute("main_window")
    manager = HostAttribute("manager")
    move_book_page = HostAttribute("move_book_page")
    presentation_destination = HostAttribute("presentation_destination")
    reader_immersive = HostAttribute("reader_immersive")
    set_book_busy = HostAttribute("set_book_busy")

    def __init__(self, owner):
        self.app = owner

    def comic_seam(self):
        return self.format_services.seam(self.book_content)

    def comic_layout_mode(self):
        if self.format_services.comic_sharing():
            return 'double'
        if self.format_services.page_region(self.book_content) is not None:
            return 'single'
        return self.format_services.mode(self.book_content)

    def comic_viewport(self):
        region = self.format_services.page_region(self.book_content)
        if region is not None:
            return region[2:]
        layout = self.book_content.layout
        return max(
            1,
            min(
                layout.content_width or self.main_window.size.width,
                self.main_window.size.width,
            ),
        ), max(1, layout.content_height or 1)

    async def move_comic(self, direction):
        if (
            self.book_busy
            or self.book_reader is None
            or self.book_record["kind"] != "comic"
        ):
            return
        index = self.book_record["position"]
        if direction > 0:
            target = self.comic_navigation.next(index)
        else:
            self.set_book_busy(True)
            try:
                target = await asyncio.to_thread(
                    self.comic_navigation.previous,
                    index,
                    viewport=self.comic_viewport(),
                    mode=self.comic_layout_mode(),
                )
            except Exception as error:
                self.book_status.text = (
                    "Cannot read previous spread: " + str(error)[:300]
                )
                return
            finally:
                self.set_book_busy(False)
        if target is not None:
            self.format_services.clear_comic_boundary()
            self.comic_navigation.requested_half = (1 if direction < 0 else 0) if target != index else (1 - self.comic_navigation.half)
            await self.move_book_page(target)
        elif self.format_services.comic_boundary is not None:
            header = getattr(self.app, 'comic_header', None)
            available = bool(header is not None and header.available[0 if direction < 0 else 1])
            await self.format_services.comic_boundary(direction,
                right_to_left=self.book_reader.right_to_left, available=available,
                adjacent=self.adjacent_book_comic)

    async def adjacent_book_comic(self, direction):
        if (
            self.book_busy
            or self.book_record is None
            or self.book_record["kind"] != "comic"
        ):
            return
        from features.comics.mobile.navigation import adjacent_comic

        key = self.book_record["id"]
        records, _ = await asyncio.to_thread(self.library_store.items)
        if (
            not self.active_host
            or self.manager.active is not self.app
            or self.book_record is None
            or self.book_record["id"] != key
        ):
            return
        target = adjacent_comic(
            [(r["id"], r["name"]) for r in records if r["kind"] == "comic"],
            self.book_record["id"],
            direction,
        )
        if target is not None:
            immersive = self.reader_immersive
            if await self.manager.open(
                target, destination=self.presentation_destination
            ):
                self.manager.active.set_reading_mode(immersive)

    async def previous_comic_file(self, widget=None, **kwargs):
        await self.adjacent_book_comic(-1)

    async def next_comic_file(self, widget=None, **kwargs):
        await self.adjacent_book_comic(1)

    def watch_comic_layout(self, reader, epoch):
        task = getattr(self, "_comic_layout_task", None)
        if task is not None and not task.done():
            return
        from features.comics.mobile.presentation import watch_layout

        async def relayout():
            self.comic_navigation.layout_reload = True
            try:
                await self.move_book_page(self.book_record['position'])
            finally:
                self.comic_navigation.layout_reload = False

        self._comic_layout_task = self.loop.create_task(
            watch_layout(
                alive=lambda: self.book_reader is reader
                and self.book_epoch == epoch
                and self.active_host,
                available=lambda: not self.book_busy
                and self.manager.active is self.app,
                viewport=lambda: (
                    self.comic_viewport(),
                    self.comic_layout_mode(),
                    self.preferences.values.get('comic_split_wide', 'true'),
                    self.format_services.comic_sharing(),
                    (self.comic_seam(), self.format_services.seam_gap(self.book_content),
                     self.format_services.page_region(self.book_content)),
                ),
                view=lambda: self.book_content.children[0]
                if self.book_content.children
                else None,
                reload=relayout,
                changed=self.format_services.layout_changed(),
                force=lambda previous, current: previous[-2:] != current[-2:],
            )
        )

    async def first_comic_page(self, widget=None, **kwargs):
        if self.book_record is not None and self.book_record["kind"] == "comic":
            await self.move_book_page(0)

    async def last_comic_page(self, widget=None, **kwargs):
        if self.book_record is not None and self.book_record["kind"] == "comic":
            await self.move_book_page(len(self.book_reader.pages) - 1)

    async def prepare_page(self, reader, record, index, epoch):
        if getattr(self, "_comic_navigation_reader", None) is not reader:
            self.comic_navigation = ComicNavigation(
                reader.read_page,
                len(reader.pages),
                double_pages=reader.double_pages,
                right_to_left=reader.right_to_left,
            )
            self.comic_navigation.requested_half = record.get('comic_half', 0)
            self._comic_navigation_reader = reader
        indices, data = await asyncio.to_thread(
            self.comic_navigation.load,
            index,
            viewport=self.comic_viewport(),
            mode=self.comic_layout_mode(),
            anchor_right=self.comic_seam() is not None,
            split_wide=(self.preferences.values.get('comic_split_wide', 'true') == 'true'
                        and not self.format_services.comic_sharing()),
        )
        if (
            epoch != self.book_epoch
            or self.book_reader is not reader
            or not self.active_host
        ):
            return
        from commonUtils.ui.native.image_canvas import ImageCanvas

        publish = None
        seam = self.format_services.seam(self.book_content)
        if len(data) == 1 and self.comic_navigation.crop is None and seam is None:
            view = page_view(
                data[0],
                canvas=ImageCanvas,
                on_page=self.swipe_book_page,
                on_toggle=self.toggle_reading_mode,
            )
        else:
            previous = (
                self.book_content.children[0] if self.book_content.children else None
            )
            if isinstance(previous, SpreadView):
                view = previous
                publish = previous.prepare_replacement(
                    data,
                    right_to_left=reader.right_to_left,
                    viewport=self.comic_viewport(),
                    seam=seam,
                    crop=self.comic_navigation.crop,
                    seam_gap=self.format_services.seam_gap(self.book_content),
                    anchor_right=seam is not None,
                )
            else:
                view = SpreadView(
                    data,
                    canvas=ImageCanvas,
                    on_page=self.swipe_book_page,
                    on_toggle=self.toggle_reading_mode,
                    right_to_left=reader.right_to_left,
                    viewport=self.comic_viewport(),
                    seam=seam,
                    crop=self.comic_navigation.crop,
                    seam_gap=self.format_services.seam_gap(self.book_content),
                    anchor_right=seam is not None,
                )
        from .presentation import place_page
        def apply():
            if publish is not None:
                publish()
            place_page(view, self.format_services.page_region(self.book_content))
        return view, indices, apply
