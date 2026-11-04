
from commonUtils.testing.stages import TestStage

from types import SimpleNamespace as NS
import unittest
from mobile import keyboard

TEST_STAGE = TestStage.REGRESSION


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


class ApplePickerRevealTests(unittest.TestCase):
    def picker(self, *, keyboard_top=204):
        from copy import copy
        from unittest.mock import Mock
        def rect(y, height):
            return NS(origin=NS(x=0, y=y), size=NS(width=570, height=height))
        class Scroll:
            bounds = rect(0, 272)
            contentSize = NS(width=570, height=230)
            layoutIfNeeded = Mock()
            scrollRectToVisible = Mock()
            def __init__(self):
                self.insets = NS(top=0, left=9, bottom=0, right=11)
                self.offset = NS(x=0, y=0)
                self.inset_writes = self.offset_writes = 0
            @property
            def contentInset(self): return copy(self.insets)
            @contentInset.setter
            def contentInset(self, value):
                self.insets = copy(value)
                self.inset_writes += 1
            @property
            def adjustedContentInset(self): return copy(self.insets)
            @property
            def contentOffset(self): return copy(self.offset)
            def convertRect(self, value, *, toView): return rect(147, 272)
            def setContentOffset(self, value, *, animated):
                self.offset = copy(value)
                self.offset_writes += 1
        scroll = Scroll()
        window = NS(layoutIfNeeded=Mock(), bounds=rect(0, 466), screen=NS(coordinateSpace=object()),
                    convertRect=lambda frame, **kwargs: frame)
        focused = NS(isFirstResponder=True, bounds=rect(0, 48),
                     isDescendantOfView=lambda owner: owner is scroll,
                     convertRect=lambda value, *, toView: rect(
                         181 - scroll.offset.y if toView is window else 34, 48))
        form = NS(_impl=NS(native=scroll), content=NS(refresh=Mock()))
        adapter = NS(keyboard_visible=True, keyboard_frame=rect(keyboard_top, 262))
        picker = NS(name_panel=None, picker_form=form,
                    save_as_name=NS(_impl=NS(native=focused)),
                    new_folder_name=NS(_impl=NS(native=NS(isFirstResponder=False))),
                    app=NS(main_window=NS(_impl=NS(native=window)), native_host=NS(adapter=adapter)))
        return picker, scroll, focused

    def test_landscape_field_is_revealed_above_actual_keyboard_without_layout_loop(self):
        picker, scroll, focused = self.picker()
        keyboard.reveal_picker_input(picker)
        field = focused.convertRect(focused.bounds, toView=picker.app.main_window._impl.native)
        self.assertGreaterEqual(field.origin.y, 147)
        self.assertLessEqual(field.origin.y + field.size.height, 204)
        self.assertTrue(focused.isFirstResponder)
        keyboard.reveal_picker_input(picker)
        self.assertEqual((scroll.inset_writes, scroll.offset_writes), (1, 1))
        picker.app.native_host.adapter.keyboard_visible = False
        keyboard.reveal_picker_input(picker)
        self.assertEqual((scroll.insets.left, scroll.insets.bottom, scroll.insets.right), (9, 0, 11))
        self.assertFalse(hasattr(picker.picker_form, '_keyboard_bottom_inset'))

    def test_uncovered_field_does_not_change_native_insets_or_scroll_position(self):
        picker, scroll, _ = self.picker(keyboard_top=430)
        keyboard.reveal_picker_input(picker)
        self.assertEqual((scroll.inset_writes, scroll.offset_writes), (0, 0))
