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
        from features.blender.library import AddonLibrary
        library = patch('features.blender.ui.page.AddonLibrary', side_effect=lambda manager: AddonLibrary(manager, provided_root=Path(self.temporary.name) / 'provided'))
        library.start(); self.addCleanup(library.stop)
        disabled = patch('features.blender.bluehole.DEFAULT', {'enabled': False, 'branch': 'main'})
        disabled.start()
        self.addCleanup(disabled.stop)
        self.builds = load_releases(platform='windows-x64')
        self.patched = patch('features.blender.ui.page.load_releases', return_value=self.builds)
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
        self.assertFalse(hasattr(page, 'install_button'))
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

    def test_launch_cards_manage_and_library_are_separate(self):
        self.manager.create_preset(self.builds[0], 'Animation')
        self.manager.create_preset(self.builds[0], 'Modeling')
        page = BlenderPage(manager=self.manager)
        self.assertEqual(len(page.launch_cards), 2)
        self.assertEqual(page.stack.currentWidget(), page.home)
        requested = []
        page.feature_settings_requested.connect(requested.append)
        page._manage_configuration(self.builds[0], 'Modeling')
        self.assertEqual(requested, ['blender'])
        self.assertEqual(page.stack.currentWidget(), page.home)
        self.assertEqual(self.manager.settings_selection, (self.builds[0].version, 'Modeling'))
        self.assertFalse(hasattr(page, 'catalog'))

    def test_settings_contains_versions_and_presets_with_default_optional_bluehole(self):
        from features.blender.settings import BlenderSettings
        self.manager.create_preset(self.builds[0], 'Art')
        with patch('features.blender.bluehole.DEFAULT', {'enabled': True, 'branch': 'main'}):
            panel = BlenderSettings(manager=self.manager)
        self.assertEqual([panel.tabs.tabText(i) for i in range(panel.tabs.count())], ['Presets', 'Versions Definitions', 'Addon Library'])
        self.assertEqual(panel.presets.stack.currentWidget(), panel.presets.preset_splitter)
        self.assertTrue(panel.presets.bluehole_enabled.isChecked())
        self.assertEqual([panel.presets.bluehole_branch.itemText(i) for i in range(3)], ['main', 'beta', 'alpha'])
        panel.presets.bluehole_enabled.setChecked(False)
        panel.presets.bluehole_branch.setCurrentText('beta')
        panel.presets._apply_addons()
        state = panel.presets.library.selection(self.manager.preset(self.builds[0], 'Art'))
        self.assertEqual(state['bluehole'], {'enabled': False, 'branch': 'beta', 'deluxe': False})
        self.assertFalse(self.manager.software.exists())

    def test_shared_library_groups_versions_and_preset_import_is_private(self):
        import zipfile
        from features.blender.settings import BlenderSettings
        self.manager.create_preset(self.builds[0], 'Art')
        self.manager.create_preset(self.builds[0], 'Other')
        panel = BlenderSettings(manager=self.manager)
        page, catalog = panel.presets, panel.library
        self.assertFalse(hasattr(catalog, 'add_button'))
        root = catalog.library.provided_root / 'Tool'
        root.mkdir(parents=True)
        for version in (1, 2):
            with zipfile.ZipFile(root / f'tool-{version}.zip', 'w') as archive:
                archive.writestr('tool/__init__.py', f'bl_info={{"name":"Tool","version":({version},0,0),"blender":(4,2,0)}}')
        personal = Path(self.temporary.name) / 'personal.zip'
        with zipfile.ZipFile(personal, 'w') as archive:
            archive.writestr('tool/__init__.py', 'bl_info={"name":"Tool","version":(3,0,0),"blender":(4,2,0)}')
        catalog.refresh()
        self.assertEqual(catalog.tree.topLevelItemCount(), 1)
        group = catalog.tree.topLevelItem(0)
        self.assertFalse(group.isExpanded())
        self.assertEqual([group.child(i).text(0) for i in range(group.childCount())], ['2.0.0', '1.0.0'])
        self.assertEqual(group.child(0).text(5), 'Shared')
        group.setExpanded(True)
        with patch('features.blender.ui.page.qt.QFileDialog.getOpenFileName', return_value=(str(personal), '')):
            page.add_addon.click()
        self._wait_for_operation(page)
        self.assertEqual(page.choices.item(0, 3).text(), '3.0.0')
        self.assertEqual(page.choices.item(0, 5).text(), 'Preset provided')
        page.preset_list.setCurrentRow(1)
        self.assertEqual(page.choices.item(0, 3).text(), '2.0.0')
        self.assertEqual(page.choices.item(0, 5).text(), 'Shared')
        catalog.refresh()
        group = catalog.tree.topLevelItem(0)
        self.assertTrue(group.isExpanded())
        self.assertEqual(group.childCount(), 2)
        self.assertTrue((root / 'tool-1.zip').exists())

    def test_preset_list_selects_same_names_in_different_versions_and_adds_to_empty_version(self):
        self.manager.create_preset(self.builds[0], 'Art')
        self.manager.create_preset(self.builds[1], 'Art')
        page = BlenderPage(manager=self.manager, settings_mode=True)
        self.assertEqual(page.preset_list.count(), 2)
        page.preset_list.setCurrentRow(1)
        self.assertEqual(page.release, self.builds[1])
        self.assertEqual(page.preset.currentText(), 'Art')
        self.assertEqual(page.preset_version_label.text(), self.builds[1].version)
        self.manager.remove_preset(self.builds[1], 'Art')
        page.refresh()
        with patch.object(page, '_preset_details', return_value=(self.builds[1].version, 'New Art')):
            page.add_preset_button.click()
        self.assertEqual(self.manager.presets(self.builds[1]), ['New Art'])
        self.assertEqual(page.preset.currentText(), 'New Art')
        self.assertEqual(page.preset_list.currentItem().data(qt.Qt.ItemDataRole.UserRole), (self.builds[1].version, 'New Art'))

    def test_addon_rows_compare_installed_and_latest_and_keep_missing_selections(self):
        import json
        import zipfile
        from features.blender.library import AddonLibrary
        root = self.manager.create_preset(self.builds[0], 'Art')
        library = AddonLibrary(self.manager, provided_root=Path(self.temporary.name) / 'provided').for_preset(root)
        addons = []
        for version in (1, 2):
            package = Path(self.temporary.name) / f'tool-{version}.zip'
            with zipfile.ZipFile(package, 'w') as archive:
                archive.writestr('tool/__init__.py', f'bl_info={{"name":"Tool","version":({version},0,0),"blender":(4,2,0)}}')
            addons.append(library.add(package))
        folder = root / 'scripts/addons/tool'; folder.mkdir()
        (folder / '__init__.py').write_text('bl_info={"name":"Tool","version":(1,0,0),"blender":(4,2,0)}')
        state = {'selected': ['legacy:tool', 'legacy:missing'], 'installed': {'legacy:tool': {
            'module': 'tool', 'path': 'scripts/addons/tool', 'digest': addons[0].digest, 'version': '1.0.0'}}}
        (root / '.logistics-addons.json').write_text(json.dumps(state))
        page = BlenderPage(manager=self.manager, settings_mode=True)
        rows = {page.choices.item(i, 0).data(qt.Qt.ItemDataRole.UserRole): i for i in range(page.choices.rowCount())}
        row = rows['legacy:tool']
        self.assertEqual(page.choices.item(row, 2).text(), '1.0.0')
        self.assertEqual(page.choices.item(row, 3).text(), '2.0.0')
        self.assertEqual(page.choices.item(row, 4).text(), 'Update available')
        self.assertEqual(page.choices.item(row, 5).text(), 'Preset provided')
        self.assertEqual(page.choices.item(rows['legacy:missing'], 4).text(), 'No compatible version')
        page.choices.item(row, 0).setCheckState(qt.Qt.CheckState.Unchecked)
        page._apply_addons()
        self.assertEqual(page.choices.item(row, 4).text(), 'Removal pending')

    def test_catalog_failure_clears_choices_and_blocks_cross_preset_save_until_refresh(self):
        import json
        import zipfile
        art = self.manager.create_preset(self.builds[0], 'Art')
        other = self.manager.create_preset(self.builds[0], 'Other')
        package = Path(self.temporary.name) / 'tool.zip'
        with zipfile.ZipFile(package, 'w') as archive:
            archive.writestr('tool/__init__.py', 'bl_info={"name":"Tool","version":(1,0,0),"blender":(3,0,0)}')
        page = BlenderPage(manager=self.manager, settings_mode=True)
        page.library.for_preset(art).add(package)
        (art / '.logistics-addons.json').write_text(json.dumps({'selected': ['legacy:tool'], 'installed': {}}))
        page.refresh()
        with patch('features.blender.library.AddonLibrary.entries', side_effect=OSError('unavailable')):
            page.preset_list.setCurrentRow(1)
            self.assertEqual(page.choices.rowCount(), 0)
            self.assertFalse(page.apply_button.isEnabled())
            page._apply_addons()
        self.assertFalse((other / '.logistics-addons.json').exists())
        page.refresh()
        self.assertTrue(page.apply_button.isEnabled())
        self.assertTrue(page.controls.isEnabled())
        self.assertEqual(page.choices.rowCount(), 0)
        provided = page.library.provided_root; provided.mkdir()
        (provided / 'broken.zip').write_bytes(b'broken')
        page.preset_list.setCurrentRow(0)
        self.assertEqual(page.choices.rowCount(), 1)
        self.assertTrue(page.apply_button.isEnabled())
        self.assertIn('broken.zip', page.catalog_warning.text())
        page._apply_addons()
        self.assertEqual(page.library.selection(art)['selected'], ['legacy:tool'])

    def test_changing_bluehole_branch_preserves_installed_branch_and_commit(self):
        import json
        root = self.manager.create_preset(self.builds[0], 'Art')
        folder = root / 'scripts/addons/BlueHole'; folder.mkdir()
        (folder / '__init__.py').write_text('bl_info={"version":(1,0,0)}')
        (root / '.logistics-addons.json').write_text(json.dumps({'selected': [], 'installed': {
            'legacy:BlueHole': {'module': 'BlueHole', 'path': 'scripts/addons/BlueHole', 'digest': 'fixture'}},
            'bluehole': {'enabled': True, 'branch': 'main', 'deluxe': False, 'commit': 'a' * 40}}))
        page = BlenderPage(manager=self.manager, settings_mode=True)
        self.assertIn('main · ' + 'a' * 12, page.bluehole_installed.text())
        page.bluehole_branch.setCurrentText('beta')
        page._apply_addons()
        state = page.library.selection(root)
        self.assertEqual(state['bluehole']['branch'], 'beta')
        self.assertEqual(state['installed_bluehole']['branch'], 'main')
        self.assertEqual(state['installed_bluehole']['commit'], 'a' * 40)
        self.assertIn('main · ' + 'a' * 12, page.bluehole_installed.text())

    def test_new_preset_dialog_collects_version_and_name_together(self):
        page = BlenderPage(manager=self.manager, settings_mode=True)
        labels = []
        def fill_dialog():
            dialog = self.app.activeModalWidget()
            form = dialog.layout()
            labels.extend(form.itemAt(row, qt.QFormLayout.ItemRole.LabelRole).widget().text() for row in range(2))
            dialog.findChild(qt.QComboBox).setCurrentText(self.builds[1].version)
            dialog.findChild(qt.QLineEdit).setText('Artist')
            dialog.accept()
        qt.QTimer.singleShot(0, fill_dialog)
        self.assertEqual(page._preset_details(), (self.builds[1].version, 'Artist'))
        self.assertEqual(labels, ['Blender version', 'Preset name'])

    def test_preset_context_menu_deletes_selected_preset_and_refreshes_list(self):
        self.manager.create_preset(self.builds[0], 'Art')
        self.manager.create_preset(self.builds[0], 'Keep')
        page = BlenderPage(manager=self.manager, settings_mode=True)
        page.resize(1000, 700)
        page.show()
        self.app.processEvents()
        item = page.preset_list.item(0)
        menu = qt.QMenu(page)
        with patch('features.blender.ui.page.qt.QMenu', return_value=menu), patch.object(menu, 'exec'):
            page._preset_context_menu(page.preset_list.visualItemRect(item).center())
        self.assertEqual([a.text() for a in menu.actions()], ['Rename…', 'Duplicate…', 'Copy to Another Version…', 'Delete…'])
        with patch.object(page, '_confirm', return_value=True):
            menu.actions()[-1].trigger()
            self._wait_for_operation(page)
        self.assertEqual(self.manager.presets(self.builds[0]), ['Keep'])
        self.assertEqual(page.preset_list.count(), 1)
        self.assertEqual(page.preset.currentText(), 'Keep')

    def _wait_for_operation(self, page):
        deadline = monotonic() + 3
        while page.task.busy and monotonic() < deadline:
            self.app.processEvents()
        self.assertFalse(page.task.busy)

    def test_first_launch_prompts_installs_and_launches_configuration(self):
        self.manager.create_preset(self.builds[0], 'Art')
        page = BlenderPage(manager=self.manager)
        self.assertTrue(page.launch_button.isEnabled())
        self.assertTrue(page.launch_cards[0].isEnabled())
        calls = []
        with patch.object(page, '_confirm', return_value=True) as confirm, \
                patch.object(self.manager, 'install', side_effect=lambda *args, **kwargs: calls.append('install')), \
                patch.object(self.manager, 'launch', side_effect=lambda *args: calls.append('launch')):
            page.launch_cards[0].click()
            self._wait_for_operation(page)
        self.assertEqual(calls, ['install', 'launch'])
        self.assertEqual(confirm.call_args.args[0],
                         f'Download and install Blender {self.builds[0].version}?\n\n'
                         f'Destination: {self.manager.installation(self.builds[0])}')

    def test_declining_first_launch_does_not_install_or_launch(self):
        self.manager.create_preset(self.builds[0], 'Art')
        page = BlenderPage(manager=self.manager)
        with patch.object(page, '_confirm', return_value=False), patch.object(self.manager, 'install') as install, patch.object(self.manager, 'launch') as launch:
            page._launch()
        install.assert_not_called()
        launch.assert_not_called()

    def test_failed_or_cancelled_install_does_not_launch(self):
        self.manager.create_preset(self.builds[0], 'Art')
        for cancel in (False, True):
            page = BlenderPage(manager=self.manager)
            def install(*args, **kwargs):
                if cancel:
                    page.task.cancelled.set()
                else:
                    raise ValueError('download failed')
            with patch.object(page, '_confirm', return_value=True), patch.object(self.manager, 'install', side_effect=install), patch.object(self.manager, 'launch') as launch:
                page._launch()
                self._wait_for_operation(page)
            launch.assert_not_called()
            self.assertIn('Cancelled' if cancel else 'download failed', page.status.text())

    def test_installed_version_launches_without_download_prompt(self):
        self.manager.create_preset(self.builds[0], 'Art')
        page = BlenderPage(manager=self.manager)
        with patch.object(self.manager, 'ready', return_value=True), patch.object(page, '_confirm') as confirm, patch.object(self.manager, 'install') as install, patch.object(self.manager, 'launch', return_value=42) as launch:
            page._launch()
        confirm.assert_not_called()
        install.assert_not_called()
        launch.assert_called_once_with(self.builds[0], 'Art')

    def test_offline_bluehole_launches_installed_copy_and_displays_warning(self):
        import zipfile
        from features.blender import bluehole
        from features.blender.library import inspect_package
        self.manager.create_preset(self.builds[0], 'Art')
        page = BlenderPage(manager=self.manager)
        package = Path(self.temporary.name) / 'bluehole.zip'
        with zipfile.ZipFile(package, 'w') as archive:
            archive.writestr('BlueHole/__init__.py', 'bl_info={"name":"Blue Hole","version":(1,0,0),"blender":(3,0,0)}')
        with patch.object(self.manager, 'executable', return_value=Path('/fixture/blender')), \
                patch('features.blender.addons.run_blender_script'), \
                patch.object(bluehole, 'update', return_value=(inspect_package(package), 'a' * 40)):
            page.library.apply(self.builds[0], 'Art', [], bluehole={'enabled': True, 'branch': 'main'})
        package.unlink()
        with patch.object(self.manager, 'ready', return_value=True), \
                patch.object(self.manager, 'executable', return_value=Path('/fixture/blender')), \
                patch('features.blender.addons.run_blender_script'), \
                patch.object(bluehole, 'resolve_branch', side_effect=ConnectionError('offline')), \
                patch.object(self.manager, 'launch', return_value=42) as launch:
            page._launch()
            self._wait_for_operation(page)
        launch.assert_called_once_with(self.builds[0], 'Art')
        self.assertIn('Using installed Blue Hole main', page.status.text())
        self.assertIn('a' * 12, page.status.text())

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
        with patch('features.blender.ui.page.inspect_addons', return_value=(rows, 'Saved state')):
            page._inspect()
            deadline = monotonic() + 3
            while page.task.busy and monotonic() < deadline:
                self.app.processEvents()
        self.assertFalse(page.task.busy)
        self.assertEqual(page.table.item(0, 3).text(), 'Yes')
        self.assertEqual(page.status.text(), 'Saved state')


if __name__ == '__main__':
    unittest.main()
