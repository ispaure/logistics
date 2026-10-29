"""Hue failures must never address a fallback group or send invalid properties."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from unittest.mock import Mock, patch
import unittest
from features.smart_home.philips_hue import api


class HueTests(unittest.TestCase):
    def bridge(self):
        bridge = Mock()
        bridge.get_group.return_value = {'1': {'name': 'Kitchen'}}
        bridge.set_group.return_value = [[{'success': {}}]]
        return bridge

    def test_missing_room_sends_no_command(self):
        bridge = self.bridge()
        with patch.object(api, 'get_bridge', return_value=bridge):
            with self.assertRaisesRegex(ValueError, 'missing'):
                api.set_group_state('Missing', True)
        bridge.set_group.assert_not_called()

    def test_combined_properties_use_one_validated_group(self):
        bridge = self.bridge()
        with patch.object(api, 'get_bridge', return_value=bridge):
            self.assertTrue(api.set_group_prop_from_arg_dict(
                {'Room': 'Kitchen', 'State': True, 'Brightness': 254, 'Color': 'Red'}))
        bridge.set_group.assert_called_once_with(1, {'on': True, 'bri': 254, 'hue': 0, 'sat': 254})

    def test_invalid_values_do_not_contact_bridge(self):
        with patch.object(api, 'get_bridge') as bridge:
            for values in ({'Brightness': 255}, {'Hue': 1}, {'State': 'yes'}, {'Color': 'Unknown'}):
                with self.assertRaises(ValueError):
                    api.set_group_prop_from_arg_dict({'Room': 'Kitchen', **values})
        bridge.assert_not_called()

    def test_bridge_error_is_not_success(self):
        bridge = self.bridge()
        bridge.set_group.return_value = [[{'error': {'description': 'not authorized'}}]]
        with patch.object(api, 'get_bridge', return_value=bridge):
            with self.assertRaisesRegex(RuntimeError, 'not authorized'):
                api.set_group_state('Kitchen', True)
