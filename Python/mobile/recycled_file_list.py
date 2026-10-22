"""Logistics appearance and theme registration for the shared recycled list."""
from functools import lru_cache
import weakref
import toga
from commonUtils.ui.native.recycled_list import RecycledList, ListAppearance, thumbnail_image
from .appearance import apple_color, android_palette, eink_enabled
from .hub_icons import icon
from .ui_metrics import TOUCH_TARGET, BODY_TEXT, CAPTION_TEXT


@lru_cache(maxsize=2)
def file_list_icon(folder):
    return thumbnail_image(icon('files' if folder else 'documents'))


class RecycledFileList(RecycledList):
    def __init__(self, *, row_kind='File', icon_kind='documents', **kwargs):
        self.icon_kind = icon_kind
        appearance = ListAppearance(palette=android_palette, apple_color=apple_color,
            high_contrast=eink_enabled, icon=lambda folder: icon('files' if folder else icon_kind),
            row_height=TOUCH_TARGET, body_text=BODY_TEXT, caption_text=CAPTION_TEXT)
        super().__init__(row_kind=row_kind, appearance=appearance, **kwargs)
        app = toga.App.app
        if not hasattr(app, '_recycled_file_lists'):
            app._recycled_file_lists = weakref.WeakSet()
        app._recycled_file_lists.add(self)


def summary_list(*, kind, icon_kind, on_select, **kwargs):
    widget = RecycledFileList(on_select=on_select, primary_action=None,
                              row_kind=kind, icon_kind=icon_kind, **kwargs)
    widget.row_icon = icon(icon_kind)
    return widget
