from types import SimpleNamespace as NS
import unittest
from mobile import keyboard


class AndroidEditorLayoutTests(unittest.TestCase):
    def test_keyboard_state_and_document_changes_invalidate_identical_native_geometry(self):
        from mobile.layout_events import native_resize_changed
        native = NS(**{name: lambda: 0 for name in ('getWidth', 'getHeight', 'getPaddingLeft',
            'getPaddingTop', 'getPaddingRight', 'getPaddingBottom', 'getVisibility')})
        backend = type('AndroidApp', (), {'__module__': 'toga_android.app'})()
        window = object()
        adapter = NS(impl=NS(native=native, native_navigationview=native), mode='bottom', keyboard_chrome=None)
        app = NS(main_window=window, _impl=backend, native_host=NS(adapter=adapter,
            state=NS(destination='documents')), body=object(), workspace=NS(active='first'))
        self.assertTrue(native_resize_changed(app, window))
        self.assertFalse(native_resize_changed(app, window))
        adapter.keyboard_chrome = object()
        self.assertTrue(native_resize_changed(app, window))
        self.assertFalse(native_resize_changed(app, window))
        adapter.keyboard_chrome = None
        self.assertTrue(native_resize_changed(app, window))
        app.workspace.active = 'second'
        self.assertTrue(native_resize_changed(app, window))

    def test_short_ime_layout_retains_controls_and_restores_after_dismissal(self):
        import toga
        from toga.style import Pack
        mode = toga.Selection(items=['Formatted', 'Source'], value='Source')
        owner = NS(source_tools=toga.Box(children=[mode]), status=toga.Label('Unsaved'))
        menu = toga.Button('Menu', style=Pack(height=52))
        save = toga.Button('Save', style=Pack(height=48))
        toolbar, editor, conflicts = toga.Box(children=[menu, save]), toga.Box(), toga.Box()
        frame = toga.Box(children=[toolbar, owner.source_tools, editor, owner.status, conflicts])
        original = list(frame.children)
        owner.document_view = toga.Box(children=[frame], style=Pack(margin=12))
        owner.toolbar = toolbar
        owner.editor = NS(_impl=NS())
        footer = toga.Box(children=[toga.Label('Private mode')])
        private = NS(crypt_markdown_footer=footer, reader_toolbar=toga.Box(), crypt_text=NS(_impl=NS()))
        private_parent = toga.Box(children=[toga.Box(), footer])
        adapter = NS(keyboard_chrome=object())
        app = NS(native_host=NS(adapter=adapter), text_views={'draft': owner},
                 private_sessions=NS(controllers={'private': private}))
        keyboard.fit_editors(app)
        self.assertIsNone(owner.source_tools.parent)
        self.assertIsNone(owner.status.parent)
        self.assertIsNone(footer.parent)
        self.assertEqual(owner.document_view.style.margin_top, 0)
        self.assertEqual(menu.style.height, 44)
        self.assertEqual(save.style.height, 44)
        toolbar.remove(save)
        self.assertIs(owner.source_tools.children[0], mode)
        self.assertEqual(mode.value, 'Source')
        self.assertEqual(frame.children, [toolbar, editor, conflicts])
        adapter.keyboard_chrome = None
        keyboard.fit_editors(app)
        self.assertEqual(frame.children, original)
        self.assertIs(footer.parent, private_parent)
        self.assertEqual(menu.style.height, 52)
        self.assertEqual(save.style.height, 48)
        self.assertEqual(owner.document_view.style.margin_top, 12)
        self.assertIs(owner.source_tools.children[0], mode)
        keyboard.fit_editors(app)
        self.assertEqual(frame.children, original)

    def test_other_backends_and_startup_are_untouched(self):
        for app in (NS(), NS(native_host=NS(adapter=None)), NS(native_host=NS(adapter=NS()))):
            keyboard.fit_editors(app)

    def test_apple_keyboard_notifies_picker_without_android_chrome(self):
        from unittest.mock import Mock
        picker = NS(fit_keyboard=Mock())
        adapter = NS(keyboard_visible=True)
        app = NS(native_host=NS(adapter=adapter), _editor_picker=picker)
        keyboard.fit_editors(app)
        picker.fit_keyboard.assert_called_once_with(True)
        adapter.keyboard_visible = False
        keyboard.fit_editors(app)
        picker.fit_keyboard.assert_called_with(False)

    def test_picker_ime_change_invalidates_unchanged_android_geometry(self):
        from unittest.mock import patch
        from mobile.layout_events import native_resize_changed
        native = NS(**{name: lambda: 0 for name in ('getWidth', 'getHeight', 'getPaddingLeft',
            'getPaddingTop', 'getPaddingRight', 'getPaddingBottom', 'getVisibility')})
        backend = type('AndroidApp', (), {'__module__': 'toga_android.app'})()
        window = object()
        adapter = NS(impl=NS(native=native, native_navigationview=native), mode='bottom', keyboard_chrome=None)
        app = NS(main_window=window, _impl=backend, _editor_picker=object(),
            native_host=NS(adapter=adapter, state=NS(destination='files')), body=object())
        with patch('mobile.keyboard.picker_keyboard_visible', return_value=False) as visible:
            self.assertTrue(native_resize_changed(app, window))
            self.assertFalse(native_resize_changed(app, window))
            visible.return_value = True
            self.assertTrue(native_resize_changed(app, window))
            self.assertFalse(native_resize_changed(app, window))

    def test_source_padding_restores_without_overwriting_a_changed_line_gutter(self):
        from toga.style import Pack
        padding = [40, 12, 4, 8]
        native = NS(getPaddingLeft=lambda: padding[0], getPaddingTop=lambda: padding[1],
                    getPaddingRight=lambda: padding[2], getPaddingBottom=lambda: padding[3],
                    setPadding=lambda *values: padding.__setitem__(slice(None), values))
        editor = NS(_impl=NS(native=native), style=Pack(margin_top=4))
        keyboard._fit_source(editor, True)
        keyboard._fit_source(editor, True)
        self.assertEqual(padding, [40, 0, 4, 0])
        self.assertEqual(editor.style.margin_top, 0)
        padding[0] = 60
        keyboard._fit_source(editor, False)
        self.assertEqual(padding, [60, 12, 4, 8])
        self.assertEqual(editor.style.margin_top, 4)
