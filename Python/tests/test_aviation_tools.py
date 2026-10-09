"""Migration coverage: feature lifecycle, every calculator, and packaged datasets."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.ui import pyside as qt
from features import aviation_tools, registry
from features.aviation_tools.location import locationUtils
from features.aviation_tools.plane import planeUtils
from features.aviation_tools.mathUtils import flightUtils
from features.aviation_tools.ui.page import AviationToolsPage, Calculator, DatasetBrowser
from ui_new import main_window


class AviationToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def page(self):
        page = AviationToolsPage()
        def cleanup():
            page.deleteLater()
            self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.addCleanup(cleanup)
        return page

    def test_feature_is_discovered_and_contributes_its_own_tab(self):
        self.assertIn('aviation_tools', registry.get_feature_names())
        with patch.object(registry, 'get_enabled_features', return_value=[aviation_tools]), \
                patch.object(main_window, 'CORE_TABS', ()):
            window = main_window.MainWindow()
            self.addCleanup(window.dlg.deleteLater)
            self.assertEqual(window.tabs.tabText(0), 'Aviation Tools')
            page = window.tabs.widget(0)
            self.assertIsInstance(page, AviationToolsPage)
            with patch.object(registry, 'get_enabled_features', return_value=[]):
                window._sync_feature_pages()
                self.assertEqual(window.tabs.count(), 0)
            window._sync_feature_pages()
            self.assertIs(window.tabs.widget(0), page)

    def test_all_original_calculators_produce_results(self):
        page = self.page()
        for name, button in page.tool_buttons.items():
            if name == 'Aircraft / Airports':
                continue
            with self.subTest(name=name):
                button.click()
                calculator = page.calculators[name]
                self.assertTrue(calculator.window().isVisible())
                self.assertFalse(calculator.window().isModal())
                calculator.calculate_button.click()
                self.assertNotIn('Cannot calculate', calculator.result.text())
                self.assertNotIn('Enter values', calculator.result.text())
        self.assertIn('NM', page.calculators['Distance'].result.text())
        self.assertIn('US gal/h', page.calculators['Cruise Performance'].result.text())

    def test_invalid_inputs_report_errors_and_allow_retry(self):
        page = self.page()
        page.open_tool('Distance')
        distance = page.calculators['Distance']
        field = distance.fields['latitude_1'][0]
        for value in ('invalid', '91', 'nan'):
            field.setText(value)
            distance.run()
            self.assertIn('Cannot calculate', distance.result.text())
        field.setText('45.60667')
        distance.run()
        self.assertIn('Distance:', distance.result.text())
        page.open_tool('KTAS → KIAS')
        speed = page.calculators['KTAS → KIAS']
        speed.fields['altitude'][0].setText('3000')
        speed.run()
        self.assertIn('Cannot calculate', speed.result.text())
        page.open_tool('KIAS → KCAS')
        calibration = page.calculators['KIAS → KCAS']
        calibration.fields['kias'][0].setText('999')
        calibration.run()
        self.assertIn('outside', calibration.result.text())
        with self.assertRaises(ValueError):
            flightUtils.magnetic_course(30, flightUtils.MagneticDeviation(10, 'invalid'))

    def test_datasets_load_from_any_working_directory_and_are_browsable(self):
        with TemporaryDirectory() as directory:
            original = Path.cwd()
            try:
                os.chdir(directory)
                self.assertEqual(len(locationUtils.get_airport_dict()), 4)
                self.assertEqual(len(planeUtils.get_aircraft_dict()), 5)
                aircraft = planeUtils.Aircraft('c-guch')
                self.assertEqual(aircraft.model.model, 'C172N')
                self.assertGreater(aircraft.model.airspeed_calibration_chart.get_kcas(107), 0)
                page = self.page()
                dialog = page.open_tool('Aircraft / Airports')
                browser = dialog.findChild(DatasetBrowser)
                self.assertEqual(browser.dataset.count(), 10)
                for index in range(browser.dataset.count()):
                    browser.dataset.setCurrentIndex(index)
                    self.assertGreater(browser.table.rowCount(), 0)
            finally:
                os.chdir(original)
        with self.assertRaisesRegex(ValueError, 'Unknown aircraft'):
            planeUtils.Aircraft('../outside')
        with self.assertRaisesRegex(ValueError, 'Unknown airport'):
            locationUtils.get_airport_from_iata('unknown')

    def test_popup_buttons_reuse_windows_and_preserve_inputs(self):
        page = self.page()
        self.assertEqual(len(page.tool_buttons), 8)
        self.assertEqual(page.findChildren(Calculator), [])
        page.tool_buttons['Distance'].click()
        distance_window = page.calculators['Distance'].window()
        page.calculators['Distance'].fields['latitude_1'][0].setText('12.5')
        distance_window.close()
        self.assertFalse(distance_window.isVisible())
        page.tool_buttons['Distance'].click()
        self.assertIs(page.calculators['Distance'].window(), distance_window)
        self.assertEqual(page.calculators['Distance'].fields['latitude_1'][0].text(), '12.5')
        page.tool_buttons['Course'].click()
        self.assertTrue(distance_window.isVisible())
        self.assertTrue(page.calculators['Course'].window().isVisible())
        self.assertEqual(len(page.findChildren(Calculator)), 2)

    def test_migrated_reference_outputs(self):
        a = flightUtils.Coordinate(0, 0)
        b = flightUtils.Coordinate(0, 1)
        self.assertAlmostEqual(flightUtils.distance_from_coords(a, b), 60.04046, places=4)
        self.assertAlmostEqual(flightUtils.true_course_from_coords(a, b), 90)
        self.assertAlmostEqual(flightUtils.ground_speed(0, 100, 0, 10), 90)
        self.assertAlmostEqual(flightUtils.ktas_to_kias(111, 2000), 108.30324, places=4)
