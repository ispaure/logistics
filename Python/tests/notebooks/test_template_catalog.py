"""Original template generation and compatibility presentation contracts."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import json
from pathlib import Path
import unittest

from commonUtils.testing.stages import TestStage
from features.notebooks import templates
from features.notebooks.editor import Editor
from features.notebooks.notebook import Notebook
from features.notebooks.remarkable_export import export_rmdoc

TEST_STAGE = TestStage.REGRESSION


class TemplateCatalogTests(unittest.TestCase):
    def test_catalog_packages_the_supplied_pdf_artwork(self):
        root = Path(templates.__file__).parent
        manifest = json.loads((root / 'mobile_sources.json').read_text())
        expected = {'assets/' + name for name in templates.DINING_ASSETS.values()}
        self.assertTrue(expected.issubset(manifest['modules']))
        for name in templates.CATALOG:
            for paper_format in templates.FORMATS:
                if name == templates.DINING_JOURNAL:
                    asset = templates.embedded_artwork(templates.native_template(name, paper_format))
                    self.assertIsInstance(asset, templates.TemplatePDF)
                    self.assertEqual(asset.paper_format, paper_format)
                    self.assertEqual(asset.data, (root / 'assets' / templates.DINING_ASSETS[paper_format]).read_bytes())
                    continue
                paths, texts = templates.geometry(name, paper_format)
                if name != 'Blank':
                    self.assertTrue(paths)
                if name.startswith('Logistics '):
                    asset = json.loads(templates.native_template(name, paper_format))
                    self.assertEqual(asset['author'], 'Logistics')
                    self.assertEqual(len(asset['items']), len(paths) + len(texts))
                    self.assertTrue(all(item['type'] in ('path', 'text') for item in asset['items']))

    def test_native_names_remain_identifiers_not_bundled_artwork(self):
        for name, count in [('P Lines small', 41), ('P Lines medium', 25), ('P Lines large', 21)]:
            book = Notebook.new()
            templates.select(book, 0, name, 'pro', True)
            result = Notebook.read(export_rmdoc(book))
            self.assertEqual(result.pages[0].template, name)
            self.assertEqual(result.content['fileType'], 'notebook')
            self.assertFalse(any(path.endswith(('.template', '.pdf')) for path in result.members))
            self.assertEqual(len(templates.geometry(name, 'pro')[0]), count)
            self.assertIn('reMarkable compatible', templates.CATALOG[name])

    def test_editor_explains_independence_and_original_backgrounds(self):
        book = Notebook.new()
        templates.select(book, 0, 'P Lines small', 'pro', True)
        state = Editor(book).state()
        self.assertIn('not affiliated with or endorsed by reMarkable', state['template_notice'])
        self.assertIn('Original Logistics', state['template_description'])
        for name in ['Logistics Checklist', 'Logistics Cornell notes', 'Logistics Weekly planner']:
            self.assertIn(name, templates.FORM_TEMPLATES)
            self.assertIn('Original Logistics', templates.description(name))
        self.assertFalse(any('workout' in name.lower() for name in templates.CATALOG))
