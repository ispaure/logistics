"""Third-party source warnings do not leak out of metadata-only inspection."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import ast
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import warnings
import zipfile

from features.blender.addons.scanning import scan_preset
from features.blender.addons.library import inspect_package
from features.blender.addons.metadata import parse_addon_source


class AddonMetadataTests(unittest.TestCase):
    def test_invalid_escape_warnings_are_scoped_to_addon_parsing(self):
        source = "bl_info={'name':'Legacy','version':(1,0,0)}\npattern='\\.'\nraise RuntimeError('not executed')\n"
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter('always')
            tree = parse_addon_source(source, 'legacy.py')
            self.assertEqual(ast.literal_eval(tree.body[0].value)['name'], 'Legacy')
            self.assertEqual(recorded, [])
            warnings.warn('invalid escape sequence from app code', SyntaxWarning)
            self.assertEqual(len(recorded), 1)
        with self.assertRaises(SyntaxError) as caught:
            parse_addon_source('bl_info = {', 'broken-addon.py')
        self.assertEqual(caught.exception.filename, 'broken-addon.py')

    def test_zip_and_preset_metadata_do_not_emit_legacy_regex_warnings(self):
        source = "bl_info={'name':'Legacy','version':(1,0,0)}\npattern='\\.'\n"
        with TemporaryDirectory() as temporary, warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter('always')
            root = Path(temporary)
            script = root / 'scripts/addons/legacy.py'
            script.parent.mkdir(parents=True)
            script.write_text(source)
            self.assertEqual(scan_preset(root)[0]['name'], 'Legacy')
            package = root / 'legacy.zip'
            with zipfile.ZipFile(package, 'w') as archive:
                archive.writestr('legacy.py', source)
            self.assertEqual(inspect_package(package).name, 'Legacy')
            self.assertEqual(recorded, [])
