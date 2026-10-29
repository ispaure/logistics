"""Keep native menu interactions alive across unchanged layout projections."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from mobile.workspace_navigation import sync_reader_toolbar


class ReaderToolbarProjectionTests(unittest.TestCase):
    def test_reflow_retains_groups_but_changed_menu_and_enabled_state_refresh(self):
        menu, image = NS(ptr=NS(value=201)), NS(ptr=NS(value=202))
        native = NS(menu=menu, imageForState=lambda state: image)
        button = NS(enabled=True, text='', accessible_name='Document actions',
                    control_icon='more', _impl=NS(native=native))
        controller = NS(ptr=NS(value=101), navigationItem=NS(title='Reader', titleView=None))
        app = NS(refresh_reader_exit=Mock(), routes=NS(apple=True), main_window=object(),
                 native_host=NS(state=NS(destination='documents'),
                                adapter=NS(content_controller=lambda destination: controller)))
        view = NS(_native_reader_buttons=lambda: [button], _native_reader_toolbar=object(),
                  _native_reader_title='Reader')
        with patch('mobile.workspace_navigation.detach'), \
                patch('mobile.reader_chrome.reader_buttons', return_value=[button]), \
                patch('mobile.ios_toolbar.vertical_edge', return_value=0), \
                patch('mobile.ios_toolbar.mount_actions') as mount:
            sync_reader_toolbar(app, view)
            sync_reader_toolbar(app, view)
            self.assertEqual(mount.call_count, 1)
            native.menu = NS(ptr=NS(value=203))
            sync_reader_toolbar(app, view)
            self.assertEqual(mount.call_count, 2)
            button.enabled = False
            sync_reader_toolbar(app, view)
            self.assertEqual(mount.call_count, 3)
            sync_reader_toolbar(app, view)
            self.assertEqual(mount.call_count, 3)


if __name__ == '__main__':
    unittest.main()
