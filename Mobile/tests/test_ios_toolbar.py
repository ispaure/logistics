"""Adaptive native bar contracts: live state, grouping, menus and pose changes."""
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock, patch

from logisticsmobile.ios_toolbar import action_groups, bar_item, mount_actions, mount_leading, vertical_edge


class Button:
    def __init__(self, icon, title):
        self.control_icon, self.accessible_name = icon, title
        self.text, self.enabled = '', True
        self._impl = NS(native=Mock(), set_enabled=Mock())
        self._impl.native.menu = None
        self._impl.native.imageForState.return_value = icon


class ToolbarTests(TestCase):
    def setUp(self):
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
        self.objc = NS(ObjCClass=lambda name: {'UIBarButtonItem': item, 'UIBarButtonItemGroup': group,
            'UIDeferredMenuElement': deferred}[name], SEL=lambda name: name, Block=lambda f, *args: f,
            ObjCBlock=lambda completion, *args: completion, objc_id=object, ns_from_py=lambda value: value)
        self.patch = patch.dict('sys.modules', {'rubicon.objc': self.objc})
        self.patch.start();self.addCleanup(self.patch.stop)
        traits = Mock(verticalBarEdge=2)
        traits.respondsToSelector.return_value = True
        self.controller = NS(traitCollection=traits, navigationItem=Mock())
        self.owner = NS()

    def test_native_items_keep_live_enabled_state_and_menu(self):
        button = Button('find', 'Search files')
        button._impl.native.menu = NS(children=['live-menu'])
        item = bar_item(button)
        self.assertIsNone(item.customView)
        self.assertEqual(item.title, 'Search files')
        self.assertIs(item.menu, button._impl.native.menu)
        button._impl.set_enabled(False)
        self.assertFalse(item.enabled)
        self.assertIs(bar_item(button), item)
        button._impl.native.menu = NS(children=['refreshed-menu'])
        self.assertIs(bar_item(button).menu, button._impl.native.menu)

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

    def test_status_and_explicit_groups_remain_separate(self):
        status, find, save, close = [Button(icon, icon) for icon in (None, 'find', 'save', 'close')]
        status._toolbar_group = 'transfer-status'
        self.assertEqual(action_groups([status, find, save, close]), [[status], [find], [save], [close]])
