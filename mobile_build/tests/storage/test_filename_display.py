"""Check mobile filename truncation, accessible names and extension-safe editing."""

from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from mobile.app import LogisticsMobile
from mobile.browser_ui import FileBrowser, middle_filename


class FilenameDisplayTests(unittest.TestCase):
    def test_apple_uses_native_middle_truncation_and_full_accessibility_name(self):
        native = SimpleNamespace(titleLabel=SimpleNamespace(lineBreakMode=4))
        impl = type('Apple', (), {'__module__': 'toga_iOS.widgets.button'})()
        impl.native = native
        button = SimpleNamespace(_impl=impl, text='Beginning ' + 'long ' * 30 + 'End.cbz')
        middle_filename(button)
        self.assertEqual(native.titleLabel.lineBreakMode, 5)
        self.assertEqual(native.accessibilityLabel, button.text)
        self.assertTrue(button.text.endswith('End.cbz'))

    def test_android_uses_single_line_middle_truncation(self):
        impl = type('Android', (), {'__module__': 'toga_android.widgets.button'})()
        impl.native = Mock()
        mode = object()
        android = SimpleNamespace(TextUtils=SimpleNamespace(TruncateAt=SimpleNamespace(MIDDLE=mode)))
        with patch.dict('sys.modules', {'android.text': android}):
            middle_filename(SimpleNamespace(_impl=impl, text='Full name.epub'))
        impl.native.setSingleLine.assert_called_once_with(True)
        impl.native.setEllipsize.assert_called_once_with(mode)
        impl.native.setContentDescription.assert_called_once_with('Full name.epub')

    def test_list_and_tiles_keep_full_name_and_provider_path(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                name = 'Beginning ' + 'long filename ' * 20 + 'Ending.cbz'
                provider = SimpleNamespace(root=Path('/virtual'), relative=lambda path: path)
                browser = FileBrowser()
                browser.set_entries(provider, '', [dict(path=name, name=name, directory=False, size=10)])
                for mode in ('List', 'Tiles'):
                    browser.mode = mode
                    browser.render()
                    entry = browser.entries[0]
                    self.assertEqual(browser.native_list.data[0].title if mode == 'List' else browser.buttons[entry.identity].text, name)
                    self.assertEqual(entry.payload['path'], name)
                app.loop.run_until_complete(browser.close())
            finally:
                app.main_window.close()
                close_loop(app.loop)
                LogisticsMobile.storage_root = None


class FilenameInputTests(unittest.TestCase):
    def test_native_editing_cannot_remove_or_replace_extension(self):
        from mobile.filename_input import FilenameInput
        for suffix in ('.txt', '.md', '.rmdoc', '.MD', '.gz'):
            with self.subTest(suffix=suffix):
                field = FilenameInput('Original' + suffix)
                self.assertEqual(field._impl.get_value(), 'Original')
                field._impl.set_value('New.version')
                self.assertEqual(field.value, 'New.version' + suffix)
                field._impl.set_value('')
                self.assertEqual(field.value, '')
                self.assertEqual(field.extension, suffix)
                field.value = 'Renamed' + suffix
                self.assertEqual(field._impl.get_value(), 'Renamed')
                self.assertEqual(field.value, 'Renamed' + suffix)

    def test_format_changes_keep_stem_and_folders_keep_dots_editable(self):
        from mobile.filename_input import FilenameInput
        field = FilenameInput('Draft.v2.txt')
        field.set_extension('.rmdoc')
        self.assertEqual(field.value, 'Draft.v2.rmdoc')
        self.assertEqual(field._impl.get_value(), 'Draft.v2')
        for name in ('Folder.v2', '.hidden', 'README'):
            field.set_filename(name, directory=name == 'Folder.v2')
            self.assertEqual(field.extension, '')
            self.assertEqual(field._impl.get_value(), name)

    def test_ios_extension_is_an_always_visible_native_accessory(self):
        from mobile.filename_input import FilenameInput
        native = SimpleNamespace(font=object())
        label = Mock()
        label_class = Mock()
        label_class.alloc.return_value.init.return_value = label
        color = SimpleNamespace(secondaryLabelColor=Mock(return_value=object()))
        module = SimpleNamespace(ObjCClass=lambda name: label_class if name == 'UILabel' else color)
        impl = type('AppleInput', (), {'__module__': 'toga_iOS.widgets.textinput'})()
        impl.native = native
        field = SimpleNamespace(extension='.rmdoc', _impl=impl)
        with patch.dict('sys.modules', {'rubicon.objc': module}):
            FilenameInput._update_suffix(field)
            self.assertIs(native.rightView, label)
            self.assertEqual(native.rightViewMode, 3)
            self.assertEqual(label.text, '.rmdoc  ')
            self.assertIs(label.textColor, color.secondaryLabelColor.return_value)
            field.extension = ''
            FilenameInput._update_suffix(field)
            self.assertIsNone(native.rightView)

    def test_android_extension_is_drawn_inside_the_input(self):
        from mobile.filename_input import FilenameInput
        native, paint, drawable = Mock(), Mock(), Mock()
        native.getTextSize.return_value = 18
        paint.measureText.return_value = 42
        paint.getFontMetrics.return_value = SimpleNamespace(ascent=-14, descent=4)
        bitmap, canvas = Mock(), Mock()
        graphics = SimpleNamespace(Bitmap=SimpleNamespace(createBitmap=Mock(return_value=bitmap),
            Config=SimpleNamespace(ARGB_8888=1)), Canvas=Mock(return_value=canvas),
            Paint=Mock(return_value=paint), Color=SimpleNamespace(rgb=Mock(return_value=128)))
        drawables = SimpleNamespace(BitmapDrawable=Mock(return_value=drawable))
        impl = type('AndroidInput', (), {'__module__': 'toga_android.widgets.textinput'})()
        impl.native = native
        field = SimpleNamespace(extension='.txt', _impl=impl)
        with patch.dict('sys.modules', {'android.graphics': graphics,
                                       'android.graphics.drawable': drawables}):
            FilenameInput._update_suffix(field)
            canvas.drawText.assert_called_once_with('.txt', 0.0, 14, paint)
            native.setCompoundDrawablesRelative.assert_called_with(None, None, drawable, None)
            native.setCompoundDrawablePadding.assert_called_with(6)
            field.extension = ''
            FilenameInput._update_suffix(field)
            native.setCompoundDrawablesRelative.assert_called_with(None, None, None, None)
