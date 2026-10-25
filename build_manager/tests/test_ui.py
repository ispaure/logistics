"""Actual Qt-to-CLI execution for a harmless second project, without Logistics."""
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

from build_manager import Phase, Plan
from build_manager.ui import ManagerPanel


class OtherProject:
    platforms = ('example',)
    operations = ('Test',)
    description = 'Synthetic second-project adapter; no cloud dependencies'
    interpreter = sys.executable
    runner_directory = Path(__file__).resolve().parents[2]

    def __init__(self, root, *, effect='test', code='print("real UI subprocess")'):
        self.results_directory = root / 'results'
        self.root, self.effect, self.code = root, effect, code

    def backend_options(self, target, operation='Test'):
        return ('Local fixture',)

    def make_plan(self, *args, **kwargs):
        return Plan('Other project', 'Test', {'revision': 'fixture'},
                    (Phase('example', (sys.executable, '-c', self.code), str(self.root)),),
                    str(self.root / 'workspace'), effect=self.effect)


class ManagerUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = TemporaryDirectory(prefix='manager-ui-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def finish(self, panel):
        deadline = time.monotonic() + 10
        while not (panel.result and panel.result.is_file() and panel.cancel.isEnabled() is False):
            self.app.processEvents()
            if time.monotonic() > deadline:
                panel.process.kill()
                panel.process.waitForFinished(1000)
                self.fail('UI did not complete its real subprocess')
            time.sleep(.01)
        return json.loads(panel.result.read_text())

    def test_ui_runs_reviewed_second_project_plan_and_shows_actual_result(self):
        panel = ManagerPanel(OtherProject(self.root))
        panel.inspect_plan()
        self.assertTrue(panel.start.isEnabled())
        panel.run_plan()
        report = self.finish(panel)
        self.assertEqual(report['status'], 'passed')
        self.assertIn('real UI subprocess', panel.preview.toPlainText())
        self.assertIn('passed', panel.status.text())
        panel.close()

    def test_declined_confirmation_launches_nothing(self):
        panel = ManagerPanel(OtherProject(self.root, effect='upload'))
        panel.inspect_plan()
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No):
            panel.run_plan()
        self.assertIsNone(panel.result)
        self.assertFalse((self.root / 'results').exists())
        panel.close()

    def test_ui_cancellation_propagates_to_child_and_retains_cancelled_result(self):
        panel = ManagerPanel(OtherProject(self.root, code='import time; time.sleep(30)'))
        panel.inspect_plan()
        panel.run_plan()
        deadline = time.monotonic() + 5
        while panel.process.state() == panel.process.ProcessState.Starting:
            self.app.processEvents()
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.01)
        # Wait for the generic CLI's signal handlers and first report.
        while not panel.result.is_file():
            self.app.processEvents()
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.01)
        panel.cancel_operation()
        self.assertEqual(self.finish(panel)['status'], 'cancelled')
        panel.close()


    def test_preflight_process_error_is_visible_without_starting_work(self):
        import subprocess
        panel=ManagerPanel(OtherProject(self.root))
        with patch.object(panel.project,'make_plan',side_effect=subprocess.CalledProcessError(3,['synthetic-read-only-preflight'])):
            panel.inspect_plan()
        self.assertIsNone(panel.plan)
        self.assertFalse(panel.start.isEnabled())
        self.assertIn('synthetic-read-only-preflight',panel.status.text())

    def test_project_supplied_option_reaches_actual_cli_and_results_opening(self):
        from PySide6.QtGui import QDesktopServices
        project = OtherProject(self.root)
        project.run_options = {'extra_probe': dict(label='Synthetic extra probe', default=True)}
        original = project.make_plan
        def make_plan(*args, **kwargs):
            self.assertNotIn('include_ipad', kwargs)
            project.code = 'print("extra enabled")' if kwargs['extra_probe'] else 'raise SystemExit(2)'
            return original(*args, **kwargs)
        project.make_plan = make_plan
        panel = ManagerPanel(project)
        panel.inspect_plan()
        panel.run_plan()
        self.assertEqual(self.finish(panel)['status'], 'passed')
        self.assertIn('extra enabled', panel.preview.toPlainText())
        with patch.object(QDesktopServices, 'openUrl', return_value=True) as opened:
            panel.open_results.click()
            self.assertEqual(opened.call_args.args[0].toLocalFile(), str(panel.result.parent))
        panel.close()

    def test_custom_secret_environment_redacts_review_before_execution(self):
        project=OtherProject(self.root)
        project.secret_environment=('SECOND_PROJECT_SECRET',)
        original=project.make_plan
        def make_plan(*args,**kwargs):
            from dataclasses import replace
            plan=original(*args,**kwargs)
            return replace(plan, source={'synthetic':os.environ['SECOND_PROJECT_SECRET']},secret_environment=project.secret_environment)
        project.make_plan=make_plan
        with patch.dict(os.environ,{'SECOND_PROJECT_SECRET':'synthetic-private-example'}):
            panel=ManagerPanel(project)
            panel.inspect_plan()
            self.assertNotIn('synthetic-private-example',panel.preview.toPlainText())
            self.assertTrue(panel.start.isEnabled())
            panel.close()
