from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from logisticsmobile.app import LogisticsMobile
from logisticsmobile.browser_ui import FileBrowser, middle_filename


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
                app.loop.close()
                LogisticsMobile.storage_root = None
