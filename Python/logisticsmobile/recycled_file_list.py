"""Recycled mobile rows: UITableView on iOS and a ListView adapter on Android.

Toga 0.5.7's Android DetailedList eagerly creates every row in a ScrollView.
Keep its public data contract, but supply an actual recycling backend there.
"""
import toga
import weakref
from functools import lru_cache


def thumbnail_image(image):
    """UITableView uses image point size to reserve label space."""
    if not type(image._impl).__module__.startswith('toga_iOS.'):
        return image
    from rubicon.objc import Block, objc_id, CGRect
    from toga_iOS.libs import UIGraphicsImageRenderer, CGSize
    from toga_iOS.images import nsdata_to_bytes
    native = image._impl.native
    renderer = UIGraphicsImageRenderer.alloc().initWithSize(CGSize(28, 28))
    def draw(context):
        ratio = min(28 / float(native.size.width), 28 / float(native.size.height))
        width, height = float(native.size.width) * ratio, float(native.size.height) * ratio
        native.drawInRect(CGRect(((28 - width) / 2, (28 - height) / 2), (width, height)))
    return toga.Image(src=nsdata_to_bytes(renderer.PNGDataWithActions(Block(draw, None, objc_id))))


@lru_cache(maxsize=2)
def file_list_icon(folder):
    from .hub_icons import icon
    return thumbnail_image(icon('files' if folder else 'documents'))


class RecycledFileList(toga.DetailedList):
    def __init__(self, *, on_visible=None, **kwargs):
        self.on_visible = on_visible
        self.updating = False
        super().__init__(primary_action='Select', secondary_action=None, **kwargs)
        app = toga.App.app
        if not hasattr(app, '_recycled_file_lists'):
            app._recycled_file_lists = weakref.WeakSet()
        app._recycled_file_lists.add(self)

    def refresh_palette(self):
        refresh = getattr(self._impl, 'refresh_palette', None)
        if refresh is not None:
            refresh()

    def _create(self):
        backend = self.factory.DetailedList.__module__
        if backend.startswith('toga_android.'):
            from .recycled_file_list_android import AndroidFileList
            return AndroidFileList(self)
        if backend.startswith('toga_iOS.'):
            from .recycled_file_list_ios import IOSFileList
            return IOSFileList(self)
        return super()._create()

    def row_visible(self, index):
        if not self.updating and self.on_visible is not None and 0 <= index < len(self.data):
            self.on_visible(self.data[index])

    @property
    def data(self):
        return toga.DetailedList.data.fget(self)

    @data.setter
    def data(self, source):
        prepare = getattr(self._impl, 'prepare_source_change', None)
        if prepare is not None:
            prepare()
        toga.DetailedList.data.fset(self, source)

    def select_index(self, index):
        """Selection changes from contextual actions must not activate a file."""
        backend = self.factory.DetailedList.__module__
        if backend.startswith('toga_android.'):
            self._impl.native.selectRow(-1 if index is None else index)
        elif backend.startswith('toga_iOS.'):
            from toga_iOS.libs import NSIndexPath
            if index is None:
                selected = self._impl.native.indexPathForSelectedRow
                if selected is not None:
                    self._impl.native.deselectRowAtIndexPath(selected, animated=False)
            else:
                path = NSIndexPath.indexPathForRow(index, inSection=0)
                self._impl.native.selectRowAtIndexPath(path, animated=False, scrollPosition=0)
        else:
            self._impl._set_value('selection', index)

    def clear(self):
        self.updating = True
        try:
            self.data = []
            self.select_index(None)
        finally:
            self.updating = False
