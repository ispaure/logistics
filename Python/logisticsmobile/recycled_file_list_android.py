"""Android bridge; all row construction/binding stays in the Java adapter."""
import weakref

from toga_android.widgets.base import Widget
from java import dynamic_proxy
from io.github.ispaure.logisticsmobile import FileListView


class AndroidFileList(Widget):
    def set_enabled(self, enabled):
        self.native.setEnabled(bool(enabled))

    def get_vertical_position(self):
        return self.native.getVerticalPosition()

    def get_max_vertical_position(self):
        return self.native.getMaxVerticalPosition()

    def set_vertical_position(self, value):
        self.native.setVerticalPosition(round(value))

    def create(self):
        self.native = FileListView(self._native_activity)
        owner = weakref.ref(self)

        class Listener(dynamic_proxy(FileListView.Listener)):
            def onActivate(self, index, generation):
                impl = owner()
                if impl is not None and generation == impl.generation:
                    impl.interface.on_select()

            def onVisible(self, index, generation):
                impl = owner()
                if impl is not None and generation == impl.generation:
                    impl.interface.row_visible(index)

            def onContext(self, index, generation):
                impl = owner()
                if impl is not None and generation == impl.generation:
                    impl.interface.on_primary_action(row=impl.interface.data[index])

        self.listener = Listener()
        self.native.setListener(self.listener)
        self.generation = 0
        self.refresh_palette()

    def refresh_palette(self):
        from android.graphics import Color
        from .appearance import android_palette, eink_enabled
        colors = android_palette(self.native.getResources().getConfiguration().uiMode & 0x30 == 0x20)
        selected_text = '#ffffff' if eink_enabled() else colors['text']
        selected_fill = '#000000' if eink_enabled() else colors['hover']
        self.native.setPalette(*[Color.parseColor(value) for value in
            (colors['text'], colors['muted'], colors['surface'], selected_text, selected_fill,
             colors['accent'], colors['border'])], eink_enabled())

    def change_source(self, source):
        self.generation += 1
        self.native.setObserveRows(bool(getattr(self.interface, 'observe_rows', False)))
        self.native.setRowKind(getattr(self.interface, 'row_kind', 'File'))
        self.native.setRows([row.title for row in source], [row.subtitle for row in source],
                            [row.folder for row in source], self.generation)
        from .hub_icons import icon
        self.native.setIcons(icon('files')._impl.native, icon(getattr(self.interface, 'icon_kind', 'documents'))._impl.native)
        for index, row in enumerate(source):
            if getattr(row, 'thumbnail', False):
                self.native.setRowIcon(index, row.icon._impl.native, self.generation)

    def source_change(self, *, item):
        if item.index < len(self.interface.data) and self.interface.data[item.index] is item:
            image = item.icon._impl.native if item.thumbnail else None
            self.native.setRowIcon(item.index, image, self.generation)

    def source_insert(self, **kwargs):
        self.change_source(self.interface.data)

    source_remove = source_insert
    source_clear = source_insert

    def get_selection(self):
        index = self.native.getCheckedItemPosition()
        return index if index >= 0 else None

    def scroll_to_row(self, row):
        self.native.setSelection(row)

    def set_refresh_enabled(self, enabled):
        pass

    def set_primary_action_enabled(self, enabled):
        self.native.setContextActions(bool(enabled))

    def set_secondary_action_enabled(self, enabled):
        pass

    def after_on_refresh(self, widget, result):
        pass
