"""Filename entry with a non-editable extension inside the native field."""
from pathlib import PurePosixPath

import toga


class FilenameInput(toga.TextInput):
    """Keep native editing/focus on the stem and expose the complete filename.

    Programmatic values may include the current suffix. Typing only ever changes
    the native stem; format selection must explicitly call ``set_extension``.
    """

    def __init__(self, value='', *, extension=None, directory=False, **kwargs):
        self.extension = '' if directory else (PurePosixPath(value).suffix if extension is None else extension)
        super().__init__(value=value, **kwargs)
        self._update_suffix()

    def _update_suffix(self):
        backend = type(self._impl).__module__
        native = getattr(self._impl, 'native', None)
        if backend.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass
            label = ObjCClass('UILabel').alloc().init()
            label.text = self.extension + '  '
            label.font = native.font
            label.textColor = ObjCClass('UIColor').secondaryLabelColor()
            label.sizeToFit()
            native.rightView = label if self.extension else None
            native.rightViewMode = 3 if self.extension else 0
        elif backend.startswith('toga_android.'):
            from android.graphics import Bitmap, Canvas, Paint, Color
            from android.graphics.drawable import BitmapDrawable
            import math
            drawable = None
            if self.extension:
                paint = Paint(3)
                paint.setTextSize(native.getTextSize())
                paint.setTypeface(native.getTypeface())
                paint.setColor(Color.rgb(128, 128, 128))
                metrics = paint.getFontMetrics()
                width = max(1, math.ceil(paint.measureText(self.extension)))
                height = max(1, math.ceil(metrics.descent - metrics.ascent))
                bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
                Canvas(bitmap).drawText(self.extension, 0.0, -metrics.ascent, paint)
                drawable = BitmapDrawable(native.getResources(), bitmap)
                drawable.setBounds(0, 0, width, height)
            native.setCompoundDrawablesRelative(None, None, drawable, None)
            native.setCompoundDrawablePadding(round(native.getTextSize() / 3))

    @property
    def value(self):
        stem = toga.TextInput.value.fget(self)
        return stem + self.extension if stem else ''

    @value.setter
    def value(self, value):
        value = str(value or '')
        if self.extension and value.endswith(self.extension):
            value = value[:-len(self.extension)]
        toga.TextInput.value.fset(self, value)

    def set_extension(self, extension):
        """Change format without changing the editable stem."""
        self.extension = extension
        self._update_suffix()

    def set_filename(self, value, *, directory=False):
        self.set_extension('' if directory else PurePosixPath(value).suffix)
        self.value = value
