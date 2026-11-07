"""Logistics appearance and theme registration for the shared recycled list."""
from functools import lru_cache
import weakref
import toga
from commonUtils.ui.native.recycled_list import RecycledList, ListAppearance, thumbnail_image
from .appearance import apple_color, android_palette, eink_enabled
from services.appearance_palette import FILE_ICON_BLUE
from .hub_icons import icon
from .ui_metrics import TOUCH_TARGET, BODY_TEXT, CAPTION_TEXT


@lru_cache(maxsize=2)
def file_list_icon(folder):
    return thumbnail_image(icon('files' if folder else 'documents'))


class RecycledFileList(RecycledList):
    def __init__(self, *, row_kind='File', icon_kind='documents', icon_size=28, title_lines=1,
                 row_height=None, body_text=BODY_TEXT, caption_text=CAPTION_TEXT, selection_role='hover', **kwargs):
        self.icon_kind = icon_kind
        if row_height is None:
            row_height = 64 if title_lines == 2 else TOUCH_TARGET

        def palette(dark):
            colors = android_palette(dark)
            return colors if selection_role == 'hover' else {**colors, 'hover': colors[selection_role]}

        def color(role):
            return apple_color(selection_role if role == 'hover' else role)

        appearance = ListAppearance(palette=palette, apple_color=color,
            high_contrast=eink_enabled, icon=lambda folder: icon('files' if folder else icon_kind),
            row_height=row_height,
            body_text=body_text, caption_text=caption_text, icon_size=icon_size, title_lines=title_lines)
        super().__init__(row_kind=row_kind, appearance=appearance, **kwargs)
        if self.factory.DetailedList.__module__.startswith('toga_android.'):
            from android.graphics import Color
            self._impl.native.setEntryIconColor(Color.parseColor(FILE_ICON_BLUE))
        app = toga.App.app
        if not hasattr(app, '_recycled_file_lists'):
            app._recycled_file_lists = weakref.WeakSet()
        app._recycled_file_lists.add(self)


def summary_list(*, kind, icon_kind, on_select, **kwargs):
    widget = RecycledFileList(on_select=on_select, primary_action=None,
                              row_kind=kind, icon_kind=icon_kind, **kwargs)
    widget.row_icon = icon(icon_kind)
    return widget
