"""The configured-folder Books & Comics panel and its native controls."""

from types import SimpleNamespace

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW


class LibraryCatalogPanel:
    """Present the retained catalogue using the library controller's state."""

    def build_library_catalog(self):
        self.library_index_status = toga.Label(
            "Metadata search · preparing index", style=Pack(font_size=12)
        )
        self.library_rows = toga.Box(style=Pack(direction=COLUMN, flex=1))
        self.library_folder_list = self.library_host.presentation.summary_list(
            kind="Library folder",
            icon_kind="files",
            on_select=self._select_library_row,
            style=Pack(flex=1),
        )
        self.library_empty = toga.Box(
            children=[
                toga.Label(
                    "No configured library folders.",
                    style=Pack(font_size=18, margin_top=16, margin_bottom=8),
                ),
                toga.Label(
                    "Import an EPUB or comic, or browse\na folder in Local or LocalCrypt.",
                    style=Pack(font_size=13, margin_bottom=12),
                ),
                self.library_host.presentation.action_button(
                    toga.Button(
                        "Import a book or comic…",
                        on_press=self.import_book,
                        style=Pack(height=48),
                    )
                ),
                toga.Button(
                    "Open Workspaces",
                    on_press=self.library_host.show_locations,
                    style=Pack(height=48),
                ),
            ],
            style=Pack(direction=COLUMN),
        )
        self.library_records = []
        self.imported_records = []
        self.imported_selected = set()
        self.library_row_buttons = []
        self.library_view = toga.Box(
            children=[
                toga.Box(
                    children=[
                        toga.Button(
                            "Refresh",
                            on_press=self.refresh_library,
                            style=Pack(height=48, flex=1),
                        ),
                        self.book_import,
                    ],
                    style=Pack(direction=ROW, margin_bottom=8),
                ),
                self.library_rows,
                self.book_status,
            ],
            style=Pack(direction=COLUMN, margin=12, flex=1),
        )
        self.book_import.text = "Import…"
        self.book_import.style.flex = 1
        self.book_import.style.height = 48
        self.book_status.style.font_size = 12
        header = self.library_view.children[0]
        refresh = header.children[0]
        refresh.accessible_name = 'Refresh library'
        refresh._toolbar_symbol = 'arrow.clockwise'
        self.book_import.accessible_name = 'Import book or comic'
        self.book_import._toolbar_symbol = 'square.and.arrow.down'
        self.library_view._ios_toolbar_buttons = [refresh, self.book_import]
        self.library_view._ios_toolbar_hidden = [header]

    def filter_library(self, widget=None, **kwargs):
        if not hasattr(self, "library_rows"):
            return
        self.library_row_buttons = []
        rows = []
        for record in self.library_records:
            from services.mobile_features import enabled
            if not enabled(self.preferences, 'comics'):
                continue
            if record['provider'].private and not enabled(self.preferences, 'rclone'):
                continue
            if not self.library_host.folder_visible(record):
                continue

            async def open_item(widget=None, library=record, **kw):
                if (
                    self.active_host
                    and not self.book_busy
                    and any(item is library for item in self.library_records)
                ):
                    if await self.library_host.open_folder(library) is False:
                        await self.refresh_library_folders()

            # Compatibility actions are lightweight models, not native controls.
            self.library_row_buttons.append(
                SimpleNamespace(
                    text=record["name"], on_press=open_item, enabled=not self.book_busy
                )
            )
            rows.append(
                dict(
                    title=record["name"],
                    subtitle=record["source"],
                    icon=self.library_folder_list.row_icon,
                    folder=True,
                    thumbnail=False,
                    entry=record,
                    callback=open_item,
                    index=len(rows),
                )
            )
        listing = self.library_folder_list
        listing.updating = True
        try:
            listing.data = rows
            listing.enabled = not self.book_busy
        finally:
            listing.updating = False
        view = listing if rows else self.library_empty
        if list(self.library_rows.children) != [view]:
            for child in list(self.library_rows.children):
                self.library_rows.remove(child)
            self.library_rows.add(view)

    def _select_library_row(self, widget, **kwargs):
        if widget.updating or self.book_busy:
            return
        row = widget.selection
        if row is not None and any(
            record is row.entry for record in self.library_records
        ):
            # Capture the command before clearing the native activation row.
            # A library folder is a launcher, not a persistent active item.
            widget.select_index(None)
            return self.loop.create_task(row.callback())
