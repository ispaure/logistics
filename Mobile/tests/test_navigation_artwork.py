"""Both Android navigation presentations receive the bundled desktop glyphs."""
from base64 import b64decode
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from logisticsmobile.hub_icons import ICONS
from logisticsmobile.navigation import DESTINATIONS, DESTINATION_ICON_NAMES, install_destination_icons


class NavigationArtworkTests(unittest.TestCase):
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
                patch('logisticsmobile.navigation.install_android_navigation_appearance'):
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
