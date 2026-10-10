"""Structured fields verified against the installed pinned rclone, using local data."""
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.process_progress import ProcessProgressWindow
from commonUtils.ui.process_runner import ProcessRunner
from features.rclone.progress import RcloneProgressParser
from features.rclone.executable import get_rclone_path


class StructuredParserTests(QtTestCase):
    def test_unknowns_active_transfers_and_error_severity_are_preserved(self):
        parser=RcloneProgressParser()
        update=parser(json.dumps({'stats':{'bytes':128,'totalBytes':1024,'eta':None,
            'transferring':[{'name':'file.bin','bytes':128,'size':1024,'speedAvg':64,'eta':14}]}}))
        self.assertIsNone(update.metrics['eta'])
        self.assertIsNone(update.metrics['files'])
        self.assertEqual(update.metrics['active_transfers'][0]['speed'],64)
        info=parser(json.dumps({'level':'info','msg':'File completed'}))
        self.assertEqual((info.done,info.total),(128,1024))
        error=parser(json.dumps({'level':'error','msg':'Connection lost'}))
        self.assertEqual(error.metrics['last_error'],'Connection lost')
        warning=parser(json.dumps({'level':'warning','msg':'Try again'}))
        self.assertEqual(warning.metrics['warnings'],1)
        parser.reset();self.assertEqual(parser.metrics,{})
        invalid=parser(json.dumps({'stats':{'bytes':'bad','totalBytes':-1,'eta':float('nan')}}))
        self.assertEqual(invalid.total,0)
        self.assertIsNone(invalid.metrics['bytes'])
        self.assertIsNone(invalid.metrics['eta'])


class RealStructuredRcloneTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.executable=get_rclone_path()
        if not cls.executable.is_file(): raise unittest.SkipTest('Pinned rclone executable not installed')
        cls.app=qt.QApplication.instance() or qt.QApplication([])

    def setUp(self):
        self.temp=TemporaryDirectory();self.root=Path(self.temp.name)
        self.config=self.root/'empty.conf';self.config.touch()
        self.source=self.root/'source';self.source.mkdir()
        self.data=b'x'*(512*1024)
        (self.source/'large.bin').write_bytes(self.data)
        (self.source/'small.txt').write_text('fixture')
        self.windows=[]

    def tearDown(self):
        for window in self.windows:
            window.runner.cancel();self.wait(lambda:not window.busy)
            window.close()
        self.app.sendPostedEvents(None,qt.QEvent.Type.DeferredDelete)
        self.temp.cleanup()

    def wait(self, condition):
        deadline=monotonic()+12
        while not condition():
            self.assertLess(monotonic(),deadline)
            self.app.processEvents();sleep(.01)
        self.app.processEvents()

    def launch(self, operation='copy', source=None, **options):
        source=source or self.source;destination=self.root/f'destination-{len(self.windows)}'
        destination.mkdir()
        if operation=='sync':(destination/'obsolete.txt').write_text('remove this fixture')
        window=ProcessProgressWindow(f'rclone {operation}',runner=ProcessRunner(parser=RcloneProgressParser()),
            context={'operation':operation.capitalize(),'source':str(source),'destination':str(destination),'dry_run':'--dry-run' in options.get('extra',[])})
        self.windows.append(window);window.show()
        updates=[];window.runner.progress.connect(updates.append)
        arguments=['--config',str(self.config),operation,'--copy-links','--use-json-log','--stats','100ms',
                   '--stats-log-level','NOTICE','--disable','Copy,Move','--bwlimit','256K','--transfers','1']
        arguments+=options.get('extra',[])
        arguments+=['--',str(source),str(destination)]
        window.start(self.executable,arguments)
        return window,destination,updates

    def test_real_copy_sync_move_update_fields_and_clear_finished_active_transfers(self):
        for operation in ('copy','sync','move'):
            with self.subTest(operation=operation):
                window,destination,updates=self.launch(operation)
                self.wait(lambda:any(update.metrics.get('active_transfers') for update in updates))
                self.assertGreater(window.active.topLevelItemCount(),0)
                self.assertFalse(window.log.isVisible())
                self.assertEqual(window.context_fields['source'].text(),str(self.source))
                self.wait(lambda:not window.busy)
                self.assertTrue(window.result.succeeded)
                self.assertEqual(window.metrics['bytes'],len(self.data)+7)
                self.assertEqual(window.metrics['files'],2)
                self.assertEqual(window.fields['files'].text(),'2 / 2')
                self.assertEqual(window.active.topLevelItemCount(),0)
                self.assertEqual(window.fields['eta'].text(),'—')
                self.assertEqual(window.bar.format(),'Complete')
                self.assertEqual((destination/'large.bin').read_bytes(),self.data)
                if operation=='sync':self.assertFalse((destination/'obsolete.txt').exists())
                if operation=='move':self.assertFalse((self.source/'large.bin').exists())
                window.logs_toggle.setChecked(True);self.assertTrue(window.log.isVisible())
                self.assertIn('"stats"',window.log.toPlainText())

    def test_actual_failure_and_cancellation_keep_exit_state_and_diagnostics(self):
        failed,destination,updates=self.launch(source=self.root/'missing')
        self.wait(lambda:not failed.busy)
        self.assertEqual(failed.result.state,'failed')
        self.assertNotEqual(failed.result.exit_code,0)
        self.assertGreater(failed.metrics.get('errors',0),0)
        self.assertIn('directory not found',failed.log.toPlainText())
        self.assertEqual(failed.active.topLevelItemCount(),0)
        cancelled,destination,updates=self.launch()
        self.wait(lambda:cancelled.metrics.get('bytes',0)>0)
        cancelled.runner.cancel();self.wait(lambda:not cancelled.busy)
        self.assertEqual(cancelled.result.state,'cancelled')
        self.assertEqual(cancelled.active.topLevelItemCount(),0)
        self.assertEqual(cancelled.fields['speed'].text(),'—')
        self.assertNotEqual(cancelled.bar.format(),'Complete')
        self.assertEqual((self.source/'large.bin').read_bytes(),self.data)

    def test_dry_run_labels_simulation_and_check_uses_counts(self):
        dry,destination,updates=self.launch(extra=['--dry-run'])
        self.wait(lambda:not dry.busy)
        self.assertTrue(dry.result.succeeded)
        self.assertFalse((destination/'large.bin').exists())
        self.assertEqual(dry.metrics['bytes'],len(self.data)+7)
        self.assertEqual(dry.statistics.layout().itemAtPosition(0,0).widget().text(),'Planned / total')
        checked,destination,updates=self.launch('check')
        # Missing destination files make check fail, and its meaningful progress
        # is checks rather than invented byte transfers.
        self.wait(lambda:not checked.busy)
        self.assertEqual(checked.result.state,'failed')
        self.assertEqual(checked.metrics['bytes'],0)
        self.assertEqual(checked.metrics['progress_basis'],'items')
