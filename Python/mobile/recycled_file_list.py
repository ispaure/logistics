"""Logistics appearance and theme registration for the shared recycled list."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from functools import lru_cache
import weakref
import toga
from commonUtils.ui.native.recycled_list import RecycledList, ListAppearance, thumbnail_image
from .appearance import apple_color, android_palette, eink_enabled
from services.appearance_palette import FILE_ICON_BLUE
from .hub_icons import icon
from .ui_metrics import TOUCH_TARGET, BODY_TEXT, CAPTION_TEXT, WRAPPED_FILENAME_ROW_HEIGHT


@lru_cache(maxsize=2)
def file_list_icon(folder):
    return thumbnail_image(icon('files' if folder else 'documents'))


class RecycledFileList(RecycledList):
    _checking_rows = False
    checked_indices = frozenset()
    selection_indicators = None

    def __init__(self, *, row_kind='File', icon_kind='documents', icon_size=28, title_lines=1,
                 row_height=None, body_text=BODY_TEXT, caption_text=CAPTION_TEXT, selection_role='hover', **kwargs):
        self.icon_kind = icon_kind
        if row_height is None:
            row_height = WRAPPED_FILENAME_ROW_HEIGHT if title_lines == 2 else TOUCH_TARGET

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

    def show_checked_rows(self, active, indices):
        indices = frozenset(indices)
        was_active = self._checking_rows
        changed = indices ^ self.checked_indices
        self._checking_rows, self.checked_indices = active, indices
        backend = self.factory.DetailedList.__module__
        if backend.startswith('toga_iOS.'):
            if active != was_active:
                self.selection_indicators = self._apple_indicators() if active else None
            if active != was_active or changed:
                self._impl.refresh_selection_indicators(None if active != was_active else changed)
        elif backend.startswith('toga_android.'):
            from android.widget import AbsListView
            native = self._impl.native
            mode = AbsListView.CHOICE_MODE_MULTIPLE if active else AbsListView.CHOICE_MODE_SINGLE
            if native.getChoiceMode() != mode:
                native.clearChoices()
                native.setChoiceMode(mode)
                icons = self._android_indicators(native) if active else (None, None)
                native.setSelectionIndicators(active, *icons)
            if active:
                native.clearChoices()
                for index in indices:
                    native.setItemChecked(index, True)
                native.invalidateViews()

    @staticmethod
    def _apple_indicators():
        from rubicon.objc import ObjCClass
        from commonUtils.ui.native.icons import apple_symbols
        scale = float(ObjCClass('UIScreen').mainScreen.scale)
        return tuple(apple_symbols((symbol,), scale).imageWithTintColor(apple_color(role), renderingMode=1)
                     for symbol, role in (('circle', 'muted'), ('checkmark.circle.fill', 'accent')))

    @staticmethod
    def _android_indicators(native):
        from android.graphics import Bitmap, Canvas
        from .control_icons import menu_drawable
        context = native.getContext()
        extent = round(24 * context.getResources().getDisplayMetrics().density)
        images = []
        for name in ('select_item', 'selected_item'):
            icon = menu_drawable(name, context)
            icon.setTint(-1)
            inset = max(1, round(extent / 12))
            icon.setBounds(inset, inset, extent - inset, extent - inset)
            image = Bitmap.createBitmap(extent, extent, Bitmap.Config.ARGB_8888)
            icon.draw(Canvas(image))
            images.append(image)
        return tuple(images)

    @property
    def selection(self):
        if self._checking_rows and self.factory.DetailedList.__module__.startswith('toga_android.'):
            # The native click selects exactly the activated row before
            # calling Toga. Android's single-selection getter is disabled in
            # multiple choice mode, so retrieve the clicked position directly.
            checked = self._impl.native.getCheckedItemPositions()
            if checked is not None and checked.size() == 1 and checked.valueAt(0):
                return self.data[checked.keyAt(0)]
            return None
        return super().selection



def summary_list(*, kind, icon_kind, on_select, **kwargs):
    widget = RecycledFileList(on_select=on_select, primary_action=None,
                              row_kind=kind, icon_kind=icon_kind, **kwargs)
    widget.row_icon = icon(icon_kind)
    return widget
