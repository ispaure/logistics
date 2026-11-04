"""Both Android navigation presentations receive the bundled desktop glyphs."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from base64 import b64decode
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from mobile.hub_icons import ICONS
from mobile.navigation import DESTINATIONS, DESTINATION_ICON_NAMES, install_destination_icons


class NavigationArtworkTests(unittest.TestCase):
    @staticmethod
    def navigation_bar():
        items = []
        for _ in DESTINATIONS:
            item = Mock()
            item.isEnabled.return_value = item.isVisible.return_value = True
            item.setEnabled.side_effect = lambda value, item=item: setattr(item.isEnabled, 'return_value', value)
            item.setVisible.side_effect = lambda value, item=item: setattr(item.isVisible, 'return_value', value)
            items.append(item)
        return NS(getMenu=lambda: NS(getItem=lambda index: items[index])), items

    def test_unchanged_visibility_does_not_invalidate_native_layout(self):
        from mobile.navigation import sync_android_destination_visibility
        bottom, items = self.navigation_bar()
        host = NS(destinations=DESTINATIONS, adapter=NS(bottom=bottom, rail=None),
                  root=NS(content=[NS(enabled=True) for key in DESTINATIONS]))
        for _ in range(3):
            sync_android_destination_visibility(host)
        for item in items:
            item.setEnabled.assert_not_called()
            item.setVisible.assert_not_called()

    def test_feature_visibility_applies_to_both_android_bars_without_removing_items(self):
        from mobile.navigation import sync_android_destination_visibility
        bottom, bottom_items = self.navigation_bar()
        rail, rail_items = self.navigation_bar()
        host = NS(destinations=DESTINATIONS, adapter=NS(bottom=bottom, rail=rail),
                  root=NS(content=[NS(enabled=key != 'chat') for key in DESTINATIONS]))
        sync_android_destination_visibility(host)
        sync_android_destination_visibility(host)
        for items in (bottom_items, rail_items):
            for index, item in enumerate(items):
                if index == 3:
                    item.setEnabled.assert_called_once_with(False)
                    item.setVisible.assert_called_once_with(False)
                else:
                    item.setEnabled.assert_not_called()
                    item.setVisible.assert_not_called()
        host.root.content[3].enabled = True
        sync_android_destination_visibility(host)
        for items in (bottom_items, rail_items):
            self.assertTrue(items[3].isEnabled())
            self.assertTrue(items[3].isVisible())

    def test_new_rail_keeps_disabled_chat_even_if_its_menu_starts_enabled(self):
        from mobile.navigation import sync_android_destination_visibility
        bottom, bottom_items = self.navigation_bar()
        rail, rail_items = self.navigation_bar()
        host = NS(destinations=DESTINATIONS, adapter=NS(bottom=bottom, rail=rail),
                  root=NS(content=[NS(enabled=True) for key in DESTINATIONS]),
                  _feature_destinations={'chat': False})
        sync_android_destination_visibility(host)
        self.assertFalse(bottom_items[3].isVisible())
        self.assertFalse(rail_items[3].isVisible())

    def test_all_destinations_use_desktop_artwork_with_independent_tint_state(self):
        bottom, rail, resources = Mock(), Mock(), Mock()
        bitmaps = [Mock() for _ in DESTINATIONS]
        drawables = [Mock() for _ in DESTINATIONS]
        factory = Mock(side_effect=bitmaps)
        drawable = Mock(side_effect=drawables)
        modules = {
            'android.util': NS(Base64=NS(DEFAULT=0, decode=lambda data, flags: b64decode(data))),
            'android.graphics': NS(BitmapFactory=NS(decodeByteArray=factory)),
            'android.graphics.drawable': NS(BitmapDrawable=drawable),
        }
        host = NS(destinations=DESTINATIONS, adapter=NS(bottom=bottom, rail=rail,
                  impl=NS(native=NS(getResources=lambda: resources))))
        with patch.dict('sys.modules', modules), \
                patch('mobile.navigation.install_android_navigation_appearance'):
            install_destination_icons(host)
        for index, key in enumerate(DESTINATIONS):
            data = b64decode(ICONS[DESTINATION_ICON_NAMES[key]])
            self.assertEqual(factory.call_args_list[index].args, (data, 0, len(data)))
            bitmaps[index].setDensity.assert_called_once_with(480)
            self.assertEqual(drawable.call_args_list[index].args, (resources, bitmaps[index]))
            # A mutable clone per bar prevents one bar's tint from affecting the other.
            self.assertEqual(drawables[index].getConstantState().newDrawable.call_count, 2)
            for bar in (bottom, rail):
                bar.getMenu().getItem.assert_any_call(index)
        self.assertEqual(factory.call_count, 5)
