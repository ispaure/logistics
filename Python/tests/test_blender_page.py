"""Blender page discovery, worker lifecycle and saved-state inventory display."""
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic
from unittest.mock import patch
import unittest

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.blender import register
from features.blender.manager import BlenderManager
from features.blender.page import BlenderPage
from features.blender.releases import load_releases


class BlenderPageTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.manager = BlenderManager(Path(self.temporary.name))
        self.builds = load_releases(platform='windows-x64')
        self.patched = patch('features.blender.page.load_releases', return_value=self.builds)
        self.patched.start()
        self.addCleanup(self.patched.stop)

    def test_page_is_discoverable_and_never_downloads_on_creation(self):
        feature = register()
        self.assertEqual(feature.id, 'blender')
        self.assertEqual(feature.pages[0].navigation_icon, 'blender')
        with patch.object(self.manager, 'install') as install:
            page = BlenderPage(manager=self.manager)
        install.assert_not_called()
        self.assertEqual(page.version.count(), 2)
        self.assertTrue(page.install_button.isEnabled())
        self.assertFalse(page.launch_button.isEnabled())
        self.assertFalse(self.manager.software.exists())

    def test_preset_selection_shows_installed_files_without_loading_addons(self):
        root = self.manager.create_preset(self.builds[0], 'Default')
        (root / 'scripts/addons/demo.py').write_text('bl_info={"name":"Demo","version":(1,0)}')
        page = BlenderPage(manager=self.manager)
        self.assertEqual(page.preset.currentText(), 'Default')
        self.assertEqual(page.table.item(0, 0).text(), 'Demo')
        self.assertEqual(page.table.item(0, 3).text(), 'Unknown')
        self.assertEqual(page.table.item(0, 4).text(), 'Preset')

    def test_close_cancels_worker_and_emits_idle_after_retirement(self):
        page = BlenderPage(manager=self.manager)
        started = Event()
        idle = []
        page.idle.connect(lambda: idle.append(True))
        def work(report, cancelled):
            started.set()
            while not cancelled():
                Event().wait(.005)
        page._run('Test operation', work)
        self.assertTrue(started.wait(2))
        self.assertFalse(page.prepare_close())
        deadline = monotonic() + 3
        while page.task.busy and monotonic() < deadline:
            self.app.processEvents()
        self.assertFalse(page.task.busy)
        self.assertTrue(page.prepare_close())
        self.assertEqual(idle, [True])
        self.assertTrue(page.controls.isEnabled())
        self.assertEqual(page.status.text(), 'Cancelled.')

    def test_inventory_refresh_displays_enabled_state(self):
        root = self.manager.create_preset(self.builds[0], 'Default')
        page = BlenderPage(manager=self.manager)
        rows = [{'name': 'Tool', 'module': 'tool', 'version': '1.0', 'kind': 'Legacy addon',
                 'enabled': True, 'path': str(root / 'scripts/addons/tool.py')}]
        with patch('features.blender.page.inspect_addons', return_value=(rows, 'Saved state')):
            page._inspect()
            deadline = monotonic() + 3
            while page.task.busy and monotonic() < deadline:
                self.app.processEvents()
        self.assertFalse(page.task.busy)
        self.assertEqual(page.table.item(0, 3).text(), 'Yes')
        self.assertEqual(page.status.text(), 'Saved state')


if __name__ == '__main__':
    unittest.main()
