"""Native list appearance follows Android theme and high-contrast changes."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from logisticsmobile.palette import DARK, EINK, LIGHT, set_eink_enabled


class AndroidFileListAppearanceTests(unittest.TestCase):
    def test_palette_refresh_updates_group_outline_and_selection_together(self):
        self.addCleanup(set_eink_enabled, False)
        modules = {
            'toga_android.widgets.base': NS(Widget=object),
            'java': NS(dynamic_proxy=lambda cls: object),
            'io.github.ispaure.logisticsmobile': NS(FileListView=object),
            'android.graphics': NS(Color=NS(parseColor=lambda value: value)),
        }
        path = Path(__file__).parents[2] / 'Python/logisticsmobile/recycled_file_list_android.py'
        spec = importlib.util.spec_from_file_location('logisticsmobile._android_list_test', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules', modules):
            spec.loader.exec_module(module)
            impl = module.AndroidFileList()
            impl.native = Mock()
            config = impl.native.getResources.return_value.getConfiguration.return_value
            for high_contrast, mode, palette in ((False, 0x10, LIGHT), (True, 0x20, EINK),
                                                   (False, 0x20, DARK)):
                set_eink_enabled(high_contrast)
                config.uiMode = mode
                impl.refresh_palette()
                colors = impl.native.setPalette.call_args.args
                self.assertEqual(colors[-2:], (palette['border'], high_contrast))
                self.assertEqual(colors[3], '#ffffff' if high_contrast else palette['text'])
                self.assertEqual(colors[4], '#000000' if high_contrast else palette['hover'])
