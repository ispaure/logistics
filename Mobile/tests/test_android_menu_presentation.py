"""Android popup themes follow current contrast; folder titles stay centered."""
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock, patch

import toga
from travertino.layout import Viewport
from logisticsmobile.action_menu import NativeMenu
from logisticsmobile.browser_ui import FolderLocationHeader
from logisticsmobile.control_icons import icon_button
from test_obsidian import ObsidianTests


class AndroidPopupTests(TestCase):
    def test_each_open_resolves_current_theme_and_keeps_native_dispatch(self):
        impl = type('AndroidButton', (), {'__module__': 'toga_android.widgets.button'})()
        impl.native = object()
        context, wrapped, popup = Mock(), Mock(), Mock()
        context.getResources.return_value.getIdentifier.side_effect = [10, 20]
        context.getPackageName.return_value = 'io.github.ispaure.logisticsmobile'
        factory = Mock(return_value=popup)
        factory.OnMenuItemClickListener = object
        wrapper = Mock(return_value=wrapped)
        callback = Mock()
        with patch.dict('sys.modules', {
                'android.widget': NS(PopupMenu=factory),
                'android.view': NS(ContextThemeWrapper=wrapper),
                'java': NS(dynamic_proxy=lambda interface: object)}), \
                patch('logisticsmobile.palette.eink_enabled', side_effect=[False, True]):
            menu = NativeMenu(NS(_impl=impl), [('Open', callback)],
                invoke=lambda action: action(), context=lambda: context, fallback=Mock())
            menu.show()
            menu.listener.onMenuItemClick(NS(getItemId=lambda: 0))
            menu.show()
            names = [call.args[0] for call in context.getResources.return_value.getIdentifier.call_args_list]
            self.assertEqual(names, ['LogisticsMenu', 'LogisticsMenuContrast'])
            self.assertEqual([call.args[1] for call in wrapper.call_args_list], [10, 20])
            factory.assert_called_with(wrapped, impl.native)
            callback.assert_called_once_with()
            menu.dispose()
            self.assertIsNone(menu.context)


class AndroidFolderTitleTests(TestCase):
    setUp = ObsidianTests.setUp
    tearDown = ObsidianTests.tearDown

    def test_title_center_survives_overflow_added_and_removed(self):
        parent = icon_button('up', 'Parent folder')
        search = icon_button('find', 'Search')
        header = FolderLocationHeader(toga.Label(''), parent, actions=[search])
        header.use_android_title()
        overflow = icon_button('overflow', 'Actions')
        for actions in ((), (overflow,), ()):
            if actions:
                header.add(*actions)
            elif overflow in header.children:
                header.remove(overflow)
            for width in (240, 390, 800):
                header.style.layout(Viewport(width, 80))
                caption = header.caption.layout
                self.assertAlmostEqual(caption.content_left + caption.content_width / 2, width / 2)
                for button in (parent, search, *actions):
                    self.assertEqual(button.layout.content_width, 48)
                    self.assertLessEqual(button.layout.content_left + 48, width)
        self.assertEqual(header.folder_name.style.font_size, 17)

    def test_storage_icons_and_text_form_one_accessible_ellipsizing_run(self):
        header = FolderLocationHeader(toga.Label(''), icon_button('up', 'Parent folder'))
        label = header.storage_identity.children[-1]
        label._impl.native = Mock()
        for image in header.storage_icons.children:
            image._impl.native = Mock()
            image._impl.scale_in = lambda value: value * 2
        text, span = Mock(), Mock()
        with patch.dict('sys.modules', {
                'android.text': NS(SpannableString=Mock(return_value=text)),
                'android.text.style': NS(ImageSpan=Mock(return_value=span))}):
            header.center_android_identity('On-device')
        self.assertEqual(header.storage_identity.children, [label])
        text.setSpan.assert_called_once_with(span, 0, 1, 33)
        header.storage_icons.children[0]._impl.native.getDrawable.return_value.setBounds.assert_called_once_with(0, 0, 24, 24)
        label._impl.native.setText.assert_called_once_with(text)
        label._impl.native.setContentDescription.assert_called_once_with('On-device folder. On-device')
