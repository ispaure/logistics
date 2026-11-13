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
        "refresh_comic_neighbors",
        "sync_comic_neighbors",
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
    _book_idle = HostAttribute("_book_idle")
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
        self.file_neighbors = (False, False)
        self._neighbor_revision = 0
        self._neighbor_opening = False

    file_entries = HostAttribute("comic_file_entries")
    open_comic_neighbor = HostAttribute("open_comic_neighbor")


    def sync_comic_neighbors(self):
        header = getattr(self.app, 'comic_header', None)
        if header is not None:
            header.sync(*(available and not self.book_busy for available in self.file_neighbors))

    async def refresh_comic_neighbors(self):
        from .navigation import adjacent_comic
        record = self.book_record
        reader = self.book_reader
        self._neighbor_revision += 1
        revision = self._neighbor_revision
        self.file_neighbors = (False, False)
        self.sync_comic_neighbors()
        self.format_services.clear_comic_boundary()
        if reader is None or record is None or record['kind'] != 'comic':
            return None, []
        token = self.app.workspace.token(self.app.session.id)
        try:
            path, entries = await asyncio.to_thread(self.file_entries)
        except (OSError, ValueError):
            return None, []
        if (revision != self._neighbor_revision or not self.active_host
                or self.book_reader is not reader or self.book_record is None
                or self.book_record['id'] != record['id']
                or not self.app.workspace.accepts(token) or self.manager.active is not self.app):
            return None, []
        if path is not None:
            self.file_neighbors = tuple(adjacent_comic(entries, path.name, direction) is not None
                                        for direction in (-1, 1))
        self.sync_comic_neighbors()
        return path, entries

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
        reader, epoch = self.book_reader, self.book_epoch
        route = self.app.navigation_generation
        navigation = getattr(self, 'comic_navigation', None)
        while self.book_busy and reader is not None and navigation is not None and navigation.layout_reload:
            # A native keyboard/chrome resize may still be fitting the page
            # after unlock returns. Preserve this navigation intent while that
            # automatic reload finishes, without applying it to a new reader.
            await self._book_idle.wait()
            if (self.book_reader is not reader or self.book_epoch != epoch
                    or not self.active_host or self.manager.active is not self.app):
                return
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
        if (self.book_reader is not reader or self.book_epoch != epoch
                or self.app.navigation_generation != route
                or not self.active_host or self.manager.active is not self.app):
            return
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
        if self._neighbor_opening:
            return
        self._neighbor_opening = True
        try:
            return await self._open_adjacent_comic(direction)
        finally:
            self._neighbor_opening = False

    async def _open_adjacent_comic(self, direction):
        if (
            self.book_busy
            or self.book_reader is None
            or self.book_record is None
            or self.book_record["kind"] != "comic"
        ):
            return
        from features.comics.mobile.navigation import adjacent_comic

        reader = self.book_reader
        route = self.app.navigation_generation
        token = self.app.workspace.token(self.app.session.id)
        # refresh_comic_neighbors starts exactly one lookup revision. A newer
        # lookup or another reader must not publish this attempt's result.
        revision = self._neighbor_revision + 1
        path, entries = await self.refresh_comic_neighbors()
        if (revision != self._neighbor_revision or self.book_reader is not reader
                or self.app.navigation_generation != route
                or not self.active_host or not self.app.workspace.accepts(token)
                or self.manager.active is not self.app):
            return
        if path is None:
            message = 'Cannot check neighboring volumes. Try again.'
            self.book_status.text = message
            return message
        target = adjacent_comic(entries, path.name, direction)
        if target is None:
            message = ('Previous' if direction < 0 else 'Next') + ' volume is no longer available.'
            self.book_status.text = message
            return message
        try:
            opened = await self.open_comic_neighbor(path.parent / target)
        except Exception:
            opened = False
        if opened:
            self.manager.close(self.app.session.id)
        elif (self.book_reader is reader and self.active_host
                and self.app.workspace.accepts(token) and self.manager.active is self.app
                and self.app.navigation_generation == route):
            self.file_neighbors = tuple(available and index != (0 if direction < 0 else 1)
                                        for index, available in enumerate(self.file_neighbors))
            self.sync_comic_neighbors()
            message = 'Could not open the neighboring volume. The current comic is still open.'
            self.book_status.text = message
            return message

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
