"""Controller ownership and operation cancellation remain independent."""
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest

from logisticsmobile.app import LogisticsMobile
from features.lm.mobile.ui import ChatUI
from features.rclone.mobile.cloud_ui import CloudUI


class WorkflowOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        LogisticsMobile.storage_root = Path(self.directory.name)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')

    def tearDown(self):
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.directory.cleanup()

    def test_feature_state_has_one_owner_and_host_access_is_explicit(self):
        app = self.app
        app.cloud_client = None
        owner = app.cloud_controller()
        self.assertIs(app.cloud_controller(), owner)
        self.assertIsNone(owner.cloud_client)
        self.assertNotIn('cloud_client', app.__dict__)
        self.assertNotIsInstance(app, (ChatUI, CloudUI))
        with self.assertRaises(AttributeError):
            getattr(owner, 'undeclared_host_service')

    def test_transfer_cancel_does_not_cancel_an_independent_file_operation(self):
        app = self.app
        file_cancel, transfer_cancel = Event(), Event()
        app._crypt_cancel = file_cancel
        app.cloud_client = None
        owner = app.transfer_controller()
        owner._transfer_cancel = transfer_cancel
        app.transfer_busy = True
        app.show_transfers()
        app.cancel_mirror_transfer()
        self.assertTrue(transfer_cancel.is_set())
        self.assertFalse(file_cancel.is_set())
        app.cancel_cloud()
        self.assertTrue(file_cancel.is_set())
