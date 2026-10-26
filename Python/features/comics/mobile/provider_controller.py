"""Feature-owned reader workflow state and explicit host dependencies."""

import asyncio
import toga
from services.workflow_host import HostAttribute


class ProviderComicController:
    METHODS = (
        "show_provider_comic_info",
        "fit_private_page",
        "move_provider_comic",
        "private_comic_seam",
        "private_comic_mode",
        "private_comic_viewport",
        "watch_provider_layout",
        "refresh_provider_comic_neighbors",
        "adjacent_provider_comic",
        "previous_provider_comic_file",
        "next_provider_comic_file",
    )
    FIELDS = (
        "_provider_viewport",
        "_provider_comic_mode",
        "_provider_comic_sharing",
        "_provider_layout_task",
        "provider_spread",
    )
    comic_header = HostAttribute("comic_header")
    crypt_content = HostAttribute("crypt_content")
    page_suspended = HostAttribute("page_suspended")
    _crypt_reader_store = HostAttribute("_crypt_reader_store")
    active_host = HostAttribute("active_host")
    cloud_busy = HostAttribute("cloud_busy")
    crypt_image = HostAttribute("crypt_image")
    crypt_immersive = HostAttribute("crypt_immersive")
    crypt_page = HostAttribute("crypt_page")
    crypt_reader = HostAttribute("crypt_reader")
    crypt_title = HostAttribute("crypt_title")
    preferences = HostAttribute("preferences")
    format_services = HostAttribute("format_services")
    loop = HostAttribute("loop")
    main_window = HostAttribute("main_window")
    manager = HostAttribute("manager")
    move_private_page = HostAttribute("move_private_page")
    presentation_destination = HostAttribute("presentation_destination")
    read_crypt_page = HostAttribute("read_crypt_page")
    session = HostAttribute("session")
    set_cloud_busy = HostAttribute("set_cloud_busy")
    workspace = HostAttribute("workspace")

    def __init__(self, owner):
        self.app = owner

    async def show_provider_comic_info(self, widget=None, **kwargs):
        if (
            self.crypt_reader is None
            or self.crypt_reader.kind not in {".cbz", ".zip"}
            or not self.manager.available(self.session.id)
        ):
            return
        path = self.format_services.comic_path(
            self._crypt_reader_store, self.crypt_reader
        )
        await self.main_window.dialog(toga.InfoDialog("Comic path", path))

    def fit_private_page(self, widget=None, **kwargs):
        view = getattr(self, "provider_spread", self.crypt_image)
        view.fit_page()
        self.format_services.notify_layout()

    async def move_provider_comic(self, direction):
        if self.cloud_busy or self.crypt_reader is None:
            return
        reader = self.crypt_reader
        index = reader.labels.index(self.crypt_page.value)
        nav = reader.comic_navigation
        if direction > 0:
            target = nav.next(index)
        else:
            self.set_cloud_busy(True)
            try:
                target = await asyncio.to_thread(
                    nav.previous,
                    index,
                    viewport=getattr(self, "_provider_viewport", (1, 1)),
                    mode=self.private_comic_mode(),
                )
            except Exception as error:
                self.crypt_title.text = self.format_services.private_label(
                    "Cannot read previous spread: " + str(error)[:200]
                )
                return
            finally:
                self.set_cloud_busy(False)
        if target is not None:
            self.format_services.clear_comic_boundary()
            nav.requested_half = (1 if direction < 0 else 0) if target != index else (1 - nav.half)
            await self.move_private_page(target)
        elif self.format_services.comic_boundary is not None:
            header = getattr(self.app, 'comic_header', None)
            available = bool(header is not None and header.available[0 if direction < 0 else 1])
            await self.format_services.comic_boundary(direction,
                right_to_left=getattr(reader, 'right_to_left', False), available=available,
                adjacent=self.adjacent_provider_comic)

    def private_comic_seam(self, view=None):
        return self.format_services.seam(getattr(view or self, 'crypt_content', self.main_window.content))

    def private_comic_mode(self):
        if self.format_services.comic_sharing():
            return 'double'
        content = getattr(self, 'crypt_content', self.main_window.content)
        if self.format_services.page_region(content) is not None:
            return 'single'
        return self.format_services.mode(
            getattr(self, "crypt_content", self.main_window.content)
        )

    def private_comic_viewport(self, view=None):
        region = self.format_services.page_region((view or self).crypt_content)
        if region is not None:
            return region[2:]
        layout = (view or self).crypt_content.layout
        return max(
            1,
            min(
                layout.content_width or self.main_window.size.width,
                self.main_window.size.width,
            ),
        ), max(1, layout.content_height or 1)

    def watch_provider_layout(self):
        task = getattr(self, "_provider_layout_task", None)
        reader = self.crypt_reader
        if (
            reader is None
            or not hasattr(reader, "comic_navigation")
            or (task is not None and not task.done())
        ):
            return
        from features.comics.mobile.presentation import watch_layout

        async def relayout():
            reader.comic_navigation.layout_reload = True
            try:
                await self.read_crypt_page()
            finally:
                reader.comic_navigation.layout_reload = False

        self._provider_layout_task = self.loop.create_task(
            watch_layout(
                alive=lambda: self.crypt_reader is reader
                and self.active_host
                and hasattr(self, "provider_spread")
                and not getattr(self, "page_suspended", False),
                available=lambda: not self.cloud_busy
                and self.manager.active is self.app,
                viewport=lambda: (
                    self.private_comic_viewport(),
                    self.private_comic_mode(),
                    self.preferences.values.get('comic_split_wide', 'true'),
                    self.format_services.comic_sharing(),
                    (self.private_comic_seam(), self.format_services.seam_gap(self.crypt_content),
                     self.format_services.page_region(self.crypt_content)),
                ),
                view=lambda: getattr(self, "provider_spread", None),
                reload=relayout,
                initial=(getattr(reader.comic_navigation, 'viewport', (1, 1)),
                         self.private_comic_mode(),
                         self.preferences.values.get('comic_split_wide', 'true'),
                         self.format_services.comic_sharing(),
                         (self.private_comic_seam(), self.format_services.seam_gap(self.crypt_content),
                          self.format_services.page_region(self.crypt_content))),
                changed=self.format_services.layout_changed(),
                force=lambda previous, current: previous[-2:] != current[-2:],
            )
        )

    async def refresh_provider_comic_neighbors(self):
        header = getattr(self, "comic_header", None)
        reader = self.crypt_reader
        provider = (getattr(self._crypt_reader_store, "provider", None)
                    or getattr(self._crypt_reader_store, "resource", None))
        if header is None or reader is None or provider is None:
            return
        header.sync(False, False)
        token = self.workspace.token(self.session.id)
        key = reader.key
        try:
            rows = await asyncio.to_thread(provider.list, key.rpartition("/")[0])
        except Exception:
            return
        if (
            not self.active_host
            or self.crypt_reader is not reader
            or not self.workspace.accepts(token)
        ):
            return
        from features.comics.mobile.navigation import adjacent_comic, folder_comics

        comics = folder_comics(rows, key)
        header.sync(
            adjacent_comic(comics, key, -1) is not None,
            adjacent_comic(comics, key, 1) is not None,
        )

    async def adjacent_provider_comic(self, direction):
        if (
            self.cloud_busy
            or self.crypt_reader is None
            or self.crypt_reader.book is not None
            or self.crypt_reader.editable
        ):
            return
        store = self._crypt_reader_store
        provider = getattr(store, "provider", None) or getattr(store, "resource", None)
        if provider is None:
            self.crypt_title.text = self.format_services.private_label(
                "Open a folder-backed comic to navigate neighboring files."
            )
            return
        from features.comics.mobile.navigation import adjacent_comic, folder_comics

        reader = self.crypt_reader
        key = reader.key
        token = self.workspace.token(self.session.id)
        try:
            rows = await asyncio.to_thread(provider.list, key.rpartition("/")[0])
        except Exception as error:
            self.crypt_title.text = self.format_services.private_label(
                "Cannot list neighboring comics: " + str(error)[:200]
            )
            return
        if (
            not self.active_host
            or self.crypt_reader is not reader
            or not self.workspace.accepts(token)
            or self.manager.active is not self.app
        ):
            return
        target = adjacent_comic(
            folder_comics(rows, key),
            key,
            direction,
        )
        if target is not None:
            immersive = self.crypt_immersive
            if await self.manager.open(
                store, target, destination=self.presentation_destination
            ):
                owner = self.manager.active
                if (owner is None or owner.crypt_reader is None
                        or owner.session.resource != self.manager.identity(store, target)):
                    return
                if owner.crypt_immersive != immersive:
                    owner.toggle_private_reading_mode()
                # Adjacent-volume reading replaces the outgoing comic. Retire it
                # only after successful publication so failures keep it readable.
                if owner is not self.app:
                    self.manager.close(self.session.id)

    async def previous_provider_comic_file(self, widget=None, **kwargs):
        await self.adjacent_provider_comic(-1)

    async def next_provider_comic_file(self, widget=None, **kwargs):
        await self.adjacent_provider_comic(1)
