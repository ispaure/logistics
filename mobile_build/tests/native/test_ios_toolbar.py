"""Adaptive native bar contracts: live state, grouping, menus and pose changes."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock, patch

from mobile.ios_toolbar import action_groups, bar_item, mount_actions, mount_leading, vertical_edge, prepare_form, supplemental_fits


class Button:
    def __init__(self, icon, title):
        self.control_icon, self.accessible_name = icon, title
        self.text, self.enabled = '', True
        self._impl = NS(native=Mock(), set_enabled=Mock())
        self._impl.native.menu = None
        self._impl.native.imageForState.return_value = icon


class ToolbarTests(TestCase):
    def setUp(self):
        color = patch('mobile.appearance.apple_color', return_value='accent')
        color.start(); self.addCleanup(color.stop)
        self.items, self.groups = [], []
        def item_factory(*args, **kwargs):
            item = Mock(customView=None, style=0)
            item.respondsToSelector.return_value = True
            self.items.append(item)
            return item
        def group_factory(items, representativeItem):
            group = NS(barButtonItems=items)
            self.groups.append(group)
            return group
        item = Mock()
        item.alloc.return_value.initWithImage.side_effect = item_factory
        item.alloc.return_value.initWithBarButtonSystemItem.side_effect = item_factory
        group = Mock()
        group.alloc.return_value.initWithBarButtonItems.side_effect = group_factory
        deferred = Mock()
        deferred.elementWithUncachedProvider.side_effect = lambda callback: callback
        action = Mock()
        action.actionWithTitle.side_effect = lambda title, **kwargs: NS(title=title, **kwargs)
        self.objc = NS(ObjCClass=lambda name: {'UIBarButtonItem': item, 'UIBarButtonItemGroup': group,
            'UIDeferredMenuElement': deferred, 'UIAction': action}[name], SEL=lambda name: name, Block=lambda f, *args: f,
            ObjCBlock=lambda completion, *args: completion, objc_id=object, ns_from_py=lambda value: value)
        self.patch = patch.dict('sys.modules', {'rubicon.objc': self.objc})
        self.patch.start();self.addCleanup(self.patch.stop)
        traits = Mock(verticalBarEdge=2)
        traits.respondsToSelector.return_value = True
        self.controller = NS(traitCollection=traits, navigationItem=Mock())
        self.owner = NS()

    def test_prominent_confirmation_uses_chosen_accent(self):
        self.assertEqual(bar_item(Button(None, 'Move here'), prominent=True).tintColor, 'accent')

    def test_supplemental_budget_tracks_system_region_without_window_resize(self):
        rect = NS(origin=NS(x=382, y=0), size=NS(width=84, height=678))
        bar = Mock(bounds=rect, items=list(range(5)))
        bar.isHidden.return_value = False
        bar.convertRect.return_value = rect
        self.controller.tabBarController = NS(tabBar=bar)
        self.controller.view = NS(bounds=rect, safeAreaInsets=NS(top=0, bottom=28))
        with patch('mobile.ios_toolbar.system_occlusions', return_value=((382, 0, 84, 160),)):
            self.assertTrue(supplemental_fits(self.controller, 1))
        with patch('mobile.ios_toolbar.system_occlusions', return_value=((382, 0, 84, 250),)):
            self.assertFalse(supplemental_fits(self.controller, 1))
        bar.isHidden.return_value = True
        self.assertTrue(supplemental_fits(self.controller, 1))

    def test_supplemental_budget_has_no_activity_height_cap(self):
        rect = NS(origin=NS(x=382, y=0), size=NS(width=84, height=678))
        bar = Mock(bounds=rect, items=list(range(5)))
        bar.isHidden.return_value = False
        bar.convertRect.return_value = rect
        self.controller.tabBarController = NS(tabBar=bar)
        self.controller.view = NS(bounds=rect, safeAreaInsets=NS(top=0, bottom=28))
        with patch('mobile.ios_toolbar.system_occlusions') as regions:
            # Extend far beyond the previously observed 250-point activity,
            # then contract without resizing the window or changing bar items.
            for height, fits in ((160, True), (250, False), (400, False),
                                 (650, False), (160, True)):
                with self.subTest(height=height):
                    regions.return_value = ((382, 0, 84, height),)
                    self.assertEqual(supplemental_fits(self.controller, 1), fits)
            # Separate activity/status reservations must use the lowest edge,
            # even if the regions arrive out of vertical order.
            regions.return_value = ((382, 220, 84, 80), (382, 0, 84, 120))
            self.assertFalse(supplemental_fits(self.controller, 1))
            regions.return_value = ((0, 0, 84, 650), (382, 0, 84, 160))
            self.assertTrue(supplemental_fits(self.controller, 1))

    def test_supplemental_moves_to_live_overflow_and_returns_when_space_recovers(self):
        find, more = Button('find', 'Search this folder'), Button('more', 'Folder actions')
        more._impl.native.menu = NS(children=['folder-action'])
        with patch('mobile.ios_toolbar.supplemental_fits', return_value=False):
            mount_actions(self.controller, self.owner, [more], supplemental=[find])
        nav = self.controller.navigationItem
        self.assertEqual(nav.leadingItemGroups, [])
        children = []
        nav.additionalOverflowItems(lambda values: children.extend(values))
        self.assertEqual(children[0].title, 'Search this folder')
        self.assertEqual(children[1], 'folder-action')
        children[0].handler(None)
        find._impl.native.performSelector.assert_called_once_with('onPress:', withObject=None)
        find.enabled = False
        nav.additionalOverflowItems(lambda values: None)
        self.assertEqual(children[0].attributes, 1)
        children[0].handler(None)
        self.assertEqual(find._impl.native.performSelector.call_count, 1)
        with patch('mobile.ios_toolbar.supplemental_fits', return_value=True):
            mount_actions(self.controller, self.owner, [more], supplemental=[find])
        self.assertEqual(nav.leadingItemGroups[0].barButtonItems, [find._ios_action_item])

    def test_native_items_keep_live_enabled_state_and_menu(self):
        button = Button('find', 'Search files')
        button._impl.native.menu = NS(children=['live-menu'])
        item = bar_item(button)
        self.assertIsNone(item.customView)
        self.assertEqual(item.title, 'Search files')
        self.assertIs(item.menu, button._impl.native.menu)
        self.assertIsNone(item.target)
        self.assertIsNone(item.action)
        button._impl.set_enabled(False)
        self.assertFalse(item.enabled)
        self.assertIs(bar_item(button), item)
        button._impl.native.menu = NS(children=['refreshed-menu'])
        self.assertIs(bar_item(button).menu, button._impl.native.menu)

    def test_context_menu_keeps_primary_action_and_removed_menu_restores_target(self):
        button = Button('more', 'Document actions')
        button._impl.native.menu = NS(children=['menu'])
        button._impl.native.showsMenuAsPrimaryAction = False
        item = bar_item(button)
        self.assertIs(item.target, button._impl.native)
        button._impl.native.showsMenuAsPrimaryAction = True
        bar_item(button)
        self.assertIsNone(item.target)
        button._impl.native.menu = None
        bar_item(button)
        self.assertIs(item.target, button._impl.native)
        self.assertEqual(item.action, 'onPress:')

    def test_close_precedes_tools_and_save_is_pinned_separately(self):
        close, save, find, more = [Button(icon, icon) for icon in ('close', 'save', 'find', 'more')]
        mount_leading(self.controller, [close], replaces_back=True)
        mount_actions(self.controller, self.owner, [save, find, more])
        nav = self.controller.navigationItem
        self.assertFalse(nav.leftItemsSupplementBackButton)
        self.assertTrue(nav.hidesBackButton)
        self.assertEqual(nav.leadingItemGroups[0].barButtonItems, [close._ios_action_item])
        self.assertEqual(nav.pinnedTrailingGroup.barButtonItems, [save._ios_action_item])
        self.assertEqual(save._ios_action_item.style, 2)
        self.assertEqual(save._ios_action_item.title, 'Save')
        self.assertIsNone(save._ios_action_item.image)
        self.assertIs(save._ios_action_item.target, save._impl.native)
        self.assertEqual(nav.trailingItemGroups[0].barButtonItems, [find._ios_action_item, more._ios_action_item])

    def test_duo_system_overflow_loads_refreshed_actions_and_restores_on_horizontal_pose(self):
        find, more = Button('find', 'Search'), Button('more', 'Actions')
        more._impl.native.menu = NS(children=['first'])
        mount_actions(self.controller, self.owner, [find, more])
        provider = self.controller.navigationItem.additionalOverflowItems
        more._impl.native.menu = NS(children=['current'])
        complete = Mock();provider(complete)
        complete.assert_called_once_with(['current'])
        self.assertEqual(self.controller.navigationItem.trailingItemGroups[0].barButtonItems, [find._ios_action_item])
        self.controller.traitCollection.verticalBarEdge = 0
        mount_actions(self.controller, self.owner, [find, more])
        self.assertIsNone(self.controller.navigationItem.additionalOverflowItems)
        self.assertEqual(self.controller.navigationItem.trailingItemGroups[0].barButtonItems,
                         [find._ios_action_item, more._ios_action_item])

    def test_older_os_and_nonvertical_context_do_not_need_device_detection(self):
        self.controller.traitCollection.respondsToSelector.return_value = False
        self.assertEqual(vertical_edge(self.controller), 0)

    def test_ios15_falls_back_to_native_item_arrays(self):
        self.controller.traitCollection.respondsToSelector.return_value = False
        self.controller.navigationItem.respondsToSelector.return_value = False
        close, save, find = [Button(icon, icon) for icon in ('close', 'save', 'find')]
        mount_leading(self.controller, [close], replaces_back=True)
        mount_actions(self.controller, self.owner, [save, find])
        self.assertEqual(self.controller.navigationItem.leftBarButtonItems, [close._ios_action_item])
        self.assertEqual(self.controller.navigationItem.rightBarButtonItems,
                         [save._ios_action_item, find._ios_action_item])

    def test_leading_projection_survives_rotation_and_reclaims_reused_controller(self):
        close = Button('close', 'Cancel')
        mount_leading(self.controller, [close], replaces_back=True)
        nav = self.controller.navigationItem
        original = nav.leadingItemGroups
        self.controller.traitCollection.verticalBarEdge = 0
        mount_leading(self.controller, [close], replaces_back=True)
        self.assertIs(nav.leadingItemGroups, original)
        close.accessible_name = 'Close configuration'
        mount_leading(self.controller, [close], replaces_back=True)
        self.assertIsNot(nav.leadingItemGroups, original)
        self.assertEqual(close._ios_action_item.title, 'Close configuration')
        owned = nav.leadingItemGroups
        nav.leadingItemGroups = []
        mount_leading(self.controller, [close], replaces_back=True)
        self.assertIsNot(nav.leadingItemGroups, owned)
        self.assertEqual(nav.leadingItemGroups[0].barButtonItems, [close._ios_action_item])
        nav.hidesBackButton = False
        mount_leading(self.controller, [close], replaces_back=True)
        self.assertTrue(nav.hidesBackButton)

    def test_legacy_leading_array_keeps_identity_until_live_state_changes(self):
        self.controller.navigationItem.respondsToSelector.return_value = False
        close = Button('close', 'Cancel')
        mount_leading(self.controller, [close], replaces_back=True)
        original = self.controller.navigationItem.leftBarButtonItems
        mount_leading(self.controller, [close], replaces_back=True)
        self.assertIs(self.controller.navigationItem.leftBarButtonItems, original)
        close.enabled = False
        mount_leading(self.controller, [close], replaces_back=True)
        self.assertFalse(close._ios_action_item.enabled)
        self.assertIsNot(self.controller.navigationItem.leftBarButtonItems, original)

    def test_system_occlusion_changes_reproject_both_sides_without_replacing_actions(self):
        close, find = Button('close', 'Close'), Button('find', 'Search')
        nav = self.controller.navigationItem
        with patch('mobile.ios_toolbar.system_occlusions', return_value=((867, 0, 84, 120),)) as regions:
            mount_leading(self.controller, [close], replaces_back=True)
            mount_actions(self.controller, self.owner, [find])
            leading, trailing = nav.leadingItemGroups, nav.trailingItemGroups
            close_item, find_item = close._ios_action_item, find._ios_action_item
            regions.return_value = ((867, 0, 84, 212),)
            mount_leading(self.controller, [close], replaces_back=True)
            mount_actions(self.controller, self.owner, [find])
            self.assertIsNot(nav.leadingItemGroups, leading)
            self.assertIsNot(nav.trailingItemGroups, trailing)
            self.assertIs(close._ios_action_item, close_item)
            self.assertIs(find._ios_action_item, find_item)
            leading, trailing = nav.leadingItemGroups, nav.trailingItemGroups
            mount_leading(self.controller, [close], replaces_back=True)
            mount_actions(self.controller, self.owner, [find])
            self.assertIs(nav.leadingItemGroups, leading)
            self.assertIs(nav.trailingItemGroups, trailing)

    def test_status_and_explicit_groups_remain_separate(self):
        status, find, save, close = [Button(icon, icon) for icon in (None, 'find', 'save', 'close')]
        status._toolbar_group = 'transfer-status'
        self.assertEqual(action_groups([status, find, save, close]), [[status], [find], [save], [close]])

    def test_unchanged_layout_keeps_menu_groups_but_reclaims_changed_controller(self):
        find, more = Button('find', 'Search'), Button('more', 'Actions')
        more._impl.native.menu = NS(children=['current'])
        mount_actions(self.controller, self.owner, [find, more])
        nav = self.controller.navigationItem
        original_groups, original_provider = nav.trailingItemGroups, nav.additionalOverflowItems
        mount_actions(self.controller, self.owner, [find, more])
        self.assertIs(nav.trailingItemGroups, original_groups)
        self.assertIs(nav.additionalOverflowItems, original_provider)
        other = NS()
        mount_actions(self.controller, other, [Button('find', 'Other document')])
        mount_actions(self.controller, self.owner, [find, more])
        self.assertEqual(nav.trailingItemGroups[0].barButtonItems, [find._ios_action_item])
        self.assertIsNot(nav.additionalOverflowItems, original_provider)
        previous = nav.trailingItemGroups
        self.controller.traitCollection.verticalBarEdge = 0
        mount_actions(self.controller, self.owner, [find, more])
        self.assertIsNot(nav.trailingItemGroups, previous)
        self.assertIsNone(nav.additionalOverflowItems)


class FormToolbarTests(TestCase):
    def test_explicit_form_actions_preserve_callbacks_and_body_actions(self):
        import toga
        primary = toga.Button('Create document', on_press=Mock())
        cancel = toga.Button('Cancel', on_press=Mock())
        erase = toga.Button('Erase all data', on_press=Mock())
        page = toga.ScrollContainer(content=toga.Box(children=[primary, erase, cancel]))
        callback = primary.on_press
        # Exercise the iOS declaration gate using real widgets; extraction occurs
        # later, when the owning native controller exists.
        with patch.object(type(page._impl), '__module__', 'toga_iOS.widgets.scrollcontainer'):
            prepare_form(page, primary='Create document', cancel='Cancel')
        self.assertEqual(page._ios_toolbar_buttons, [primary])
        self.assertEqual(page._ios_toolbar_leading, [cancel])
        self.assertTrue(page._ios_toolbar_replaces_back)
        self.assertIs(primary.on_press, callback)
        self.assertIn(erase, page.content.children)
        self.assertFalse(hasattr(erase, '_toolbar_prominent'))

    def test_declared_form_wraps_and_unwraps_when_safe_width_changes(self):
        import toga
        from mobile.ios_toolbar import fit_form
        label = toga.Label('Exclusions apply only to Push; excluded destination files are kept.')
        save = toga.Button('Save settings')
        page = toga.Box(children=[label, save])
        with patch.object(type(page._impl), '__module__', 'toga_iOS.widgets.box'):
            prepare_form(page, primary='Save settings')
        app = NS(adaptive=NS(content_width=Mock(return_value=350)))
        fit_form(app, page, 'files')
        self.assertIn('\n', label.text)
        app.adaptive.content_width.return_value = 1200
        fit_form(app, page, 'files')
        self.assertEqual(label.text, label._settings_source_text)
        self.assertNotIn('\n', label.text)
        self.assertIs(page.children[0], label)

    def test_android_keeps_form_content_unchanged(self):
        import toga
        button = toga.Button('Save settings')
        page = toga.Box(children=[button])
        prepare_form(page, primary='Save settings')
        self.assertFalse(hasattr(page, '_ios_toolbar_buttons'))
        self.assertEqual(list(page.children), [button])
