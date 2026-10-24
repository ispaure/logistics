"""Folder identity follows actual storage and root navigation returns to the Hub."""
from unittest.mock import AsyncMock, patch
import unittest

import toga
from mobile.browser_ui import FolderLocationHeader
from mobile.control_icons import icon_button
from mobile_build.tests.documents.test_obsidian import ObsidianTests


class FolderLocationTests(unittest.TestCase):
    setUp = ObsidianTests.setUp
    tearDown = ObsidianTests.tearDown
    run_async = ObsidianTests.run_async

    def test_header_replaces_source_identity_when_location_changes(self):
        button = icon_button('up', 'Parent folder')
        header = FolderLocationHeader(toga.Label('Folder path'), button)
        for path, online, encrypted, unlocked, expected in (
                ('', False, False, False, ['storage_local']),
                ('Books', True, True, False, ['storage_remote', 'folder_locked']),
                ('Books', True, True, True, ['storage_remote', 'folder_unlocked']),
                ('Books', False, True, True, ['storage_local', 'folder_unlocked']),
                ('Books', False, True, False, ['storage_local', 'folder_locked']),
                ('', True, False, True, ['storage_remote']),
                ('', False, False, False, ['storage_local'])):
            header.update(path, remote=online, encrypted=encrypted, unlocked=unlocked)
            self.assertEqual([child.control_icon for child in header.storage_icons.children], expected)
            if encrypted:
                indicator = header.storage_icons.children[-1]
                self.assertEqual(indicator._impl._surface_roles[1], expected[-1])
                self.assertEqual(indicator.accessible_name, 'Encrypted folder, ' + ('unlocked' if unlocked else 'locked'))
            self.assertNotIn(header.storage_icons, header.children)
            self.assertTrue(all(isinstance(child, toga.ImageView) for child in header.storage_icons.children))
            header.status.text = ''
            header.refresh_status()
            self.assertEqual(header.caption.children, [header.folder_name, header.storage_identity])
            self.assertEqual(header.storage_identity.children[-1].value,
                             ('Cloud' if online else 'On-device') +
                             ((' · Unlocked' if unlocked else ' · Locked') if encrypted else '') +
                             (' · LocalCrypt' if encrypted and not online else ''))
            self.assertEqual(button.control_icon, 'back')
            self.assertEqual(button.accessible_name, 'Back')

    def test_localcrypt_root_uses_folder_name_and_loaded_session_status(self):
        from types import SimpleNamespace
        from mobile.folder_navigation import FolderScreen
        provider = SimpleNamespace(private=True, remote='Secret', client=SimpleNamespace(
            package_records=[dict(remotes=['Secret'], saved=False)]))
        header = FolderLocationHeader(toga.Label(''), icon_button('up', 'Parent folder'))
        header.update_provider('', provider, name='LocalCrypt: Secret (pulled)')
        self.assertEqual(header.folder_name.value, 'Secret')
        self.assertEqual(header.storage_identity.children[-1].value,
                         'On-device · Unlocked (Session Only) · LocalCrypt')
        screen = FolderScreen(None, SimpleNamespace(search_provider=provider), None,
                              'LocalCrypt: Secret (pulled)', '', 'browser')
        self.assertEqual(screen.title, 'Secret')
        provider.client.package_records[0]['saved'] = True
        header.update_provider('', provider)
        self.assertEqual(header.storage_identity.children[-1].value,
                         'On-device · Unlocked · LocalCrypt')
        screen.path = 'Books/Reference'
        self.assertEqual(screen.title, 'Reference')

    def test_ios_description_scrolls_full_text_and_centers_short_text(self):
        import sys
        from types import SimpleNamespace as NS
        from unittest.mock import Mock
        from mobile.folder_title import mount

        for measured_width in (30, 400):
            with self.subTest(measured_width=measured_width):
                instances = {}
                def factory(name):
                    def new(*args):
                        view = Mock()
                        view.sizeThatFits.return_value = NS(width=measured_width)
                        instances.setdefault(name, []).append(view)
                        return view
                    allocated = Mock()
                    allocated.init.side_effect = new
                    allocated.initWithFrame.side_effect = new
                    allocated.initWithImage.side_effect = new
                    cls = Mock()
                    cls.alloc.return_value = allocated
                    return cls
                backend = type('HeaderImpl', (), {'__module__': 'toga_iOS.widgets.box'})()
                header = Mock(_impl=backend, _storage_kinds=[('storage_local', ''), ('folder_unlocked', '')],
                              storage_identity=NS(children=[NS(text='On-device · Unlocked (Session Only) · LocalCrypt')]),
                              window=NS(_impl=NS(native=NS(bounds=NS(size=NS(width=390))))))
                controller = NS(navigationItem=NS())
                objc = NS(ObjCClass=factory, CGRect=lambda origin, size: (origin, size),
                          CGSize=lambda width, height: (width, height))
                with patch.dict(sys.modules, {'rubicon.objc': objc}), \
                        patch('mobile.folder_title.mount_actions'), \
                        patch('mobile.appearance.apple_color'), \
                        patch('mobile.hub_icons.icon'):
                    mount(header, controller, 'Secret')
                scroll = instances['UIScrollView'][0]
                self.assertEqual(scroll.contentSize[1], 15)
                self.assertGreaterEqual(scroll.contentSize[0], measured_width)
                self.assertEqual(scroll.contentSize[0] > 174, measured_width > 174)
                scroll.addSubview.assert_called_once_with(instances['UIStackView'][0])
                self.assertEqual(instances['UILabel'][-1].text,
                                 'On-device · Unlocked (Session Only) · LocalCrypt')

    def test_root_navigation_returns_to_hub_even_when_cloud_busy(self):
        self.app.show_cloud(present=False)
        self.run_async(self.app.show_files(local_root=True))
        self.app.file_path = self.app.cloud_path = ''
        self.app.cloud_busy = True
        with patch.object(self.app, 'show_locations') as hub:
            self.run_async(self.app.parent_file_folder())
            self.run_async(self.app.parent_cloud())
            self.assertEqual(hub.call_count, 2)

    def test_plain_location_label_and_search_toggle_live_in_header(self):
        from mobile.browser_ui import FileBrowser
        browser = FileBrowser()
        status = browser.status_label('Current folder')
        header = browser.attach_location_header(status, icon_button('up', 'Parent folder'))
        self.assertIsInstance(status, toga.Label)
        self.assertEqual(status.value, 'Current folder')
        self.assertEqual(header.children[-1], browser.search_button)
        self.assertEqual(header.children, [header.parent_button, header.caption, browser.search_button])
        self.assertEqual(header.caption.children, [header.folder_name, status])
        self.assertEqual(browser.search_button.control_icon, 'find')
        self.assertNotIn(browser.navigation_controls, browser.widget.children)
        self.assertNotIn(browser.search_panel, browser.widget.children)
        original = list(header.children)
        browser.search_button.on_press()
        self.assertEqual(header.children, original)
        self.assertIs(browser.search_panel.parent, browser.widget)
        self.assertTrue(browser.search_open)
        browser.search.value = 'test'
        browser.close_search_button.on_press()
        self.assertEqual(browser.search.value, '')
        self.assertNotIn(browser.search_panel, browser.widget.children)
        self.assertEqual(header.children, original)
        self.assertFalse(browser.search_open)

    def test_native_title_actions_leave_no_idle_row_and_search_keeps_menu_in_bar(self):
        from mobile.browser_ui import FileBrowser
        browser = FileBrowser()
        header = browser.attach_location_header(browser.status_label(''), icon_button('up', 'Parent folder'))
        overflow = icon_button('more', 'Folder actions')
        header.add(overflow)
        header.use_native_title()
        header._native_title_mounted = True
        header.refresh_status()
        self.assertEqual(header.title_actions, (browser.search_button, overflow))
        self.assertEqual(header.children, [])
        browser.toggle_search()
        self.assertEqual(header.native_actions.children, [browser.search_panel])
        self.assertEqual(header.children, [header.native_actions])
        self.assertIsNone(overflow.parent)
        self.assertNotIn(browser.search_panel, browser.widget.children)
        browser.open_search()  # Refocusing must not overwrite the saved controls.
        browser.toggle_search()
        self.assertEqual(header.native_actions.children, [])
        self.assertEqual(header.children, [])
        self.assertFalse(browser.search_open)
        header.status.value = 'Refreshing folder…'
        self.assertEqual(header.children, [header.caption])
        header.status.value = ''
        self.assertEqual(header.children, [])

    def test_ios_search_releases_keyboard_before_detaching_the_field(self):
        from unittest.mock import Mock
        from mobile.browser_ui import FileBrowser
        browser = FileBrowser()
        browser.open_search()
        native = Mock()
        native.resignFirstResponder.side_effect = lambda: self.assertTrue(browser.search_open)
        with patch.object(type(browser.search._impl), '__module__', 'toga_iOS.widgets.textinput'), \
                patch.object(browser.search._impl, 'native', native, create=True):
            browser.close_search()
        native.resignFirstResponder.assert_called_once()
        self.assertFalse(browser.search_open)

    def test_standalone_search_retains_fixed_height_row(self):
        from mobile.browser_ui import FileBrowser
        browser = FileBrowser()
        browser.toggle_search()
        self.assertIs(browser.search_panel.parent, browser.widget)
        self.assertEqual(browser.search_panel.style.flex, 0)
        browser.toggle_search()
        self.assertFalse(browser.search_open)

    def test_parent_remote_navigation_stays_in_current_storage(self):
        self.app.show_cloud(present=False)
        self.app.cloud_busy = False
        self.app.cloud_path = 'Books/Reference'
        with patch.object(self.app, 'browse_cloud', new=AsyncMock(return_value=True)) as browse, \
                patch.object(self.app, 'show_locations') as hub:
            self.run_async(self.app.parent_cloud())
            self.assertEqual(self.app.cloud_location.value, 'Books')
            browse.assert_awaited_once()
            hub.assert_not_called()

    def test_long_native_folder_and_status_labels_leave_search_on_screen(self):
        from mobile.browser_ui import FileBrowser
        from travertino.layout import Viewport
        from travertino.size import at_least

        def native_measure(impl):
            impl.interface.intrinsic.width = at_least(600)
            impl.interface.intrinsic.height = 24

        label_backend = type(toga.Label('')._impl)
        with patch.object(label_backend, 'rehint', native_measure, create=True):
            browser = FileBrowser()
            header = browser.attach_location_header(browser.status_label(''), icon_button('up', 'Parent folder'))
            overflow = icon_button('overflow', 'File and folder actions')
            header.add(overflow)
            header.update('A very long folder name that cannot fit beside navigation')
            for message in ('', 'A long operation message that must truncate'):
                header.status.value = message
                for label in (header.folder_name, header.status, header.storage_identity.children[-1]):
                    label._impl.rehint()
                for width in (240, 320, 600):
                    with self.subTest(message=message, width=width):
                        header.style.layout(Viewport(width, 80))
                        search = browser.search_button.layout
                        self.assertLessEqual(search.content_left + search.content_width, width)
                        self.assertEqual(search.content_width, 48)
                        more = overflow.layout
                        self.assertLessEqual(more.content_left + more.content_width, width)
                        self.assertEqual(more.content_width, 48)
                        self.assertEqual(more.content_top, search.content_top)
                        self.assertGreater(header.folder_name.layout.content_width, 0)
                        if not message:
                            subtitle = header.storage_identity.children[-1].layout
                            self.assertGreater(subtitle.content_width, 1)
                            self.assertGreaterEqual(subtitle.content_height, 24)
                            self.assertGreaterEqual(header.storage_identity.layout.content_height, 24)
                        else:
                            self.assertGreaterEqual(header.status.layout.content_height, 24)

    def test_local_drawer_search_stays_beside_current_folder(self):
        drawer = self.app.adaptive.browser('documents')
        browser = drawer.browser
        header = browser.location_bar
        self.assertIn(header, drawer.browser_widget.children)
        self.assertIs(drawer.breadcrumb, header.folder_name)
        self.assertIs(header.children[-1], browser.search_button)
        self.assertNotIn(browser.navigation_controls, browser.widget.children)
        original = list(header.children)
        browser.search_button.on_press()
        self.assertEqual(header.children, original)
        self.assertIs(browser.search_panel.parent, browser.widget)
        self.assertTrue(browser.search_open)
        browser.close_search_button.on_press()
        self.assertNotIn(browser.search_panel, browser.widget.children)

    def test_hub_transfer_banner_only_reports_relevant_rclone_work(self):
        self.app.show_cloud(present=False)
        self.app.folder_source = 'rclone'
        view = self.app.build_folder_picker()
        bar = view.transfer_banner
        self.app.transfer_notification = False
        self.app.transfer_busy = True
        self.app.refresh_transfer_status()
        self.assertIn(bar, view.children)
        for source in ('Local', 'Network shares', 'rclone'):
            self.app.change_folder_source(source)
            self.assertEqual(bar in view.children, source == 'rclone')
        self.app.transfer_busy = False
        self.app.transfer_notification = self.app.transfer_complete = True
        self.app.refresh_transfer_status()
        self.assertNotIn(bar, view.children)
        self.app.transfer_complete = False
        self.app.refresh_transfer_status()
        self.assertIn(bar, view.children)
        self.app.dismiss_transfer_status()
        self.assertNotIn(bar, view.children)
