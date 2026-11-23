"""Check mobile filename truncation, accessible names and extension-safe editing."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

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


    def test_local_tile_filename_uses_card_width_and_keeps_item_actions(self):
        from mobile.file_browser_view import LocalFileBrowser
        from mobile_build.tests.support.app import create_app

        app = create_app(self)
        opened, folders, actions = [], [], []
        browser = LocalFileBrowser(open_file=opened.append, open_folder=folders.append,
                                   item_actions=actions.append)
        self.addCleanup(lambda: app.loop.run_until_complete(browser.close()))
        provider = SimpleNamespace(root=Path('/virtual'), relative=lambda path: path)
        folder = '000 - Collections and preliminary notes from the field'
        names = ['001 - ' + 'wide field notes ' * 8 + 'rev-α.cbz',
                 '002-' + '測定🧪' * 30 + '-final.tar.gz']
        files = [folder, *names, *(f'{index:03}-dense-file.md' for index in range(3, 168))]
        browser.set_entries(provider, '', [dict(path=name, name=name, directory=name == folder)
                                           for name in files])
        browser.show_tiles()
        entries = browser._tile_entries[:3]
        for width in (224, 320, 540, 768, 1024):
            with self.subTest(width=width):
                # Width is for the browser pane, after any rail, sidebar or hinge.
                browser.items.style.layout(SimpleNamespace(width=width, height=600))
                for entry in entries:
                    _, card, title, _, _ = browser._tile_cards[entry.identity]
                    band, _ = card.children
                    media, menu = band.children
                    self.assertEqual(title.layout.content_width, card.children[1].layout.content_width)
                    self.assertIsNone(card._tile_selection.parent)
                    self.assertGreaterEqual(title.layout.content_height, 64)
                    self.assertLessEqual(menu.layout.absolute_content_top + menu.layout.content_height,
                                         title.layout.absolute_content_top)
                    self.assertEqual(menu.layout.content_width, 48)
                    self.assertEqual(menu.layout.content_height, 48)
                    self.assertLessEqual(media.layout.absolute_content_left + media.layout.content_width,
                                         menu.layout.absolute_content_left)
                    self.assertEqual(title.accessible_name, entry.label)
                    self.assertEqual(menu.accessible_name, 'Actions for ' + entry.label)
                row = browser._tile_row_views[0]
                self.assertLessEqual(row.children[-1].layout.absolute_content_left
                                     + row.children[-1].layout.content_width, width)

        dir_entry, file_entry, _ = entries
        file_card = browser._tile_cards[file_entry.identity][1]
        menu = file_card.children[0].children[1]
        title = file_card.children[-1].children[-1]
        app.loop.run_until_complete(menu.on_press())
        self.assertEqual([row['path'] for row in actions], [names[0]])
        self.assertFalse(opened)
        app.loop.run_until_complete(title.on_press())
        self.assertEqual([row['path'] for row in opened], [names[0]])
        app.loop.run_until_complete(browser.buttons[dir_entry.identity].on_press())
        self.assertEqual([row['path'] for row in folders], [folder])

        browser.on_check_entry = lambda entry: None
        browser.checked_entries = {file_entry.identity}
        browser.highlight_selection()
        _, file_card, title, _, _ = browser._tile_cards[file_entry.identity]
        self.assertEqual(file_card._tile_selection.accessible_name, 'Deselect ' + names[0])
        browser.checked_entries.clear()
        browser.on_check_entry = None
        browser.highlight_selection()
        title = browser.buttons[file_entry.identity]
        self.assertEqual(title.accessible_name, names[0])

        browser._update_tile_window(browser.TILE_ROW_HEIGHT * 80)
        self.assertLessEqual(len(browser._tile_cards), 80)
        self.assertIn(browser._tile_entries[-1].identity, browser._tile_cards)
        self.assertEqual(title.text, '')

    def test_android_tile_fits_second_line_with_longest_suffix(self):
        from mobile.file_browser_view import _android_tile_title

        name = 'Project 🧪 notes and measurements for review – revision 03.tar.gz'
        units = name.encode('utf-16-le')
        line_end = len('Project 🧪 '.encode('utf-16-le')) // 2
        obtain = Mock()
        obtain.return_value.build.return_value = SimpleNamespace(
            getLineCount=lambda: 4, getLineEnd=lambda line: line_end)
        paint = Mock()
        paint.measureText.return_value = 260
        middle, start = object(), object()
        ellipsize = Mock(return_value='…revision 03.tar.gz')
        android = SimpleNamespace(
            StaticLayout=SimpleNamespace(Builder=SimpleNamespace(obtain=obtain)),
            TextUtils=SimpleNamespace(TruncateAt=SimpleNamespace(MIDDLE=middle, START=start), ellipsize=ellipsize,
                substring=lambda text, start, end: units[start * 2:end * 2].decode('utf-16-le')))
        with patch.dict('sys.modules', {'android.text': android}):
            self.assertEqual(_android_tile_title(name, paint, 110, 2), 'Project 🧪\n…revision 03.tar.gz')
            obtain.assert_called_once_with(name, 0, len(units) // 2, paint, 110)
            ellipsize.assert_called_once_with(name[len('Project 🧪 '):], paint, 110.0, start)
            obtain.return_value.build.return_value.getLineCount = lambda: 2
            self.assertEqual(_android_tile_title(name, paint, 210, 2), name)
            self.assertEqual(_android_tile_title(name, paint, 110, 1), '…revision 03.tar.gz')
            ellipsize.assert_called_with(name, paint, 110.0, middle)
            obtain.return_value.build.return_value.getLineCount = lambda: 4
            paint.measureText.return_value = 20
            paint.breakText.return_value = line_end + 7
            boundaries = Mock()
            boundaries.preceding.return_value = line_end + 7
            icu = SimpleNamespace(BreakIterator=SimpleNamespace(getCharacterInstance=lambda: boundaries))
            with patch.dict('sys.modules', {'android.icu.text': icu}):
                self.assertEqual(_android_tile_title(name, paint, 110, 2),
                                 'Project 🧪 notes a\n…revision 03.tar.gz')
            boundaries.setText.assert_called_once_with(name)
            boundaries.preceding.assert_called_once_with(line_end + 8)


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
