import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from logisticsmobile import keyboard


class AppleKeyboardTests(unittest.TestCase):
    def delegate(self):
        class NativeObject:
            def __init_subclass__(cls, protocols=()):
                pass

            @classmethod
            def alloc(cls):
                return cls()

            def init(self):
                return self

        gesture = NS()
        def objc_class(name):
            if name == 'NSObject':
                return NativeObject
            if name == 'UITapGestureRecognizer':
                return NS(alloc=lambda: NS(initWithTarget=lambda *args, **kwargs: gesture))
            return name

        native = NS(addGestureRecognizer=Mock())
        implementation = type('Window', (), {'__module__': 'toga_iOS.window'})()
        implementation.native = native
        app = NS(main_window=NS(_impl=implementation))
        objc = NS(ObjCClass=objc_class, ObjCProtocol=lambda name: name,
                  objc_method=lambda method: method, SEL=lambda name: name)
        with patch.object(keyboard, '_apple_delegate', None), patch.dict(sys.modules, {'rubicon.objc': objc}):
            keyboard.install(app)
        self.assertFalse(gesture.cancelsTouchesInView)
        return app._keyboard_delegate

    def view(self, kind, parent=None, *, editable=True, getters=False, window=None):
        value = lambda item: (lambda: item) if getters else item
        return NS(isKindOfClass=lambda name: name == kind,
                  superview=value(parent), editable=value(editable), window=value(window))

    def test_outside_tap_handles_properties_and_getters_without_consuming_touch(self):
        delegate = self.delegate()
        for getters in (False, True):
            with self.subTest(getters=getters):
                window = NS(endEditing=Mock())
                parent = self.view('UIView', getters=getters)
                leaf = self.view('UIButton', parent, getters=getters, window=window)
                touch = NS(view=(lambda: leaf) if getters else leaf)
                self.assertFalse(delegate.gestureRecognizer_shouldReceiveTouch_(None, touch))
                window.endEditing.assert_called_once_with(True)

    def test_text_controls_and_web_content_keep_keyboard_and_selection(self):
        delegate = self.delegate()
        for kind, editable in (('UITextField', True), ('UITextView', True), ('WKWebView', False)):
            for getters in (False, True):
                with self.subTest(kind=kind, getters=getters):
                    window = NS(endEditing=Mock())
                    parent = self.view(kind, editable=editable, getters=getters)
                    leaf = self.view('UIView', parent, getters=getters, window=window)
                    self.assertFalse(delegate.gestureRecognizer_shouldReceiveTouch_(None, NS(view=leaf)))
                    window.endEditing.assert_not_called()

    def test_detached_or_missing_touch_view_is_safe(self):
        delegate = self.delegate()
        for leaf in (None, self.view('UIView')):
            self.assertFalse(delegate.gestureRecognizer_shouldReceiveTouch_(None, NS(view=leaf)))


class AndroidEditorLayoutTests(unittest.TestCase):
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


class AndroidBrowserBindingTests(unittest.TestCase):
    def test_retained_controls_keep_one_listener_and_new_rows_dismiss_without_consuming_touch(self):
        class View:
            OnTouchListener = object
            def __init__(self):
                self.setOnTouchListener = Mock()
        class ViewGroup(View):
            def __init__(self, children=()):
                super().__init__()
                self.children = list(children)
            def getChildCount(self):
                return len(self.children)
            def getChildAt(self, index):
                return self.children[index]
        class EditText(View):
            pass
        class Impl:
            __module__ = 'toga_android.widgets.box'
            def __init__(self, native):
                self.native = native
        def widget(native, children=()):
            return NS(_impl=Impl(native), children=list(children))

        search_native = EditText()
        search_native.hasFocus = Mock(return_value=True)
        search_native.clearFocus = Mock()
        search_native.getWindowToken = Mock(return_value='token')
        search = widget(search_native)
        button_native = View()
        button = widget(button_native)
        root_native = ViewGroup([search_native, button_native])
        root = widget(root_native, [search, button])
        browser = NS(search=search, widget=root)
        modules = {
            'android.content': NS(Context=NS(INPUT_METHOD_SERVICE='ime')),
            'android.view': NS(View=View, ViewGroup=ViewGroup, MotionEvent=NS(ACTION_DOWN=0)),
            'android.widget': NS(EditText=EditText),
            'java': NS(dynamic_proxy=lambda interface: object),
        }
        with patch.dict(sys.modules, modules):
            keyboard.bind_browser(browser)
            listener = browser._keyboard_touch
            keyboard.bind_browser(browser)
            self.assertIs(browser._keyboard_touch, listener)
            root_native.setOnTouchListener.assert_called_once_with(listener)
            button_native.setOnTouchListener.assert_called_once_with(listener)
            search_native.setOnTouchListener.assert_not_called()

            internal_label = View()
            new_native = ViewGroup([internal_label])
            new = widget(new_native)
            root.children.append(new)
            root_native.children.append(new_native)
            keyboard.bind_browser(browser, roots=[new])
            keyboard.bind_browser(browser)
            new_native.setOnTouchListener.assert_called_once_with(listener)
            internal_label.setOnTouchListener.assert_called_once_with(listener)
            button_native.setOnTouchListener.assert_called_once_with(listener)
            manager = NS(hideSoftInputFromWindow=Mock())
            new_native.getContext = lambda: NS(getSystemService=lambda kind: manager)
            self.assertFalse(listener.onTouch(new_native, NS(getAction=lambda: 0)))
            search_native.clearFocus.assert_called_once()
            manager.hideSoftInputFromWindow.assert_called_once_with('token', 0)
