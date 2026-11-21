"""Folder workers preserve cancellation, generation and private-path boundaries."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from threading import Event
from types import SimpleNamespace as NS
import unittest
from commonUtils.runtime.operations import OperationCancelled
from desktop.pages.folder_controller import FolderController
from models.folder_entry import FolderEntry


class FolderControllerTests(unittest.TestCase):
    def test_work_captures_generation_before_a_later_refresh(self):
        controller = FolderController(refresh_generation=3)
        work = controller.discovery_work(('remote',), ('local',), lambda **kw: kw)
        controller.refresh_generation = 4
        generation, result = work(None, Event().is_set)
        self.assertEqual(generation, 3)
        self.assertEqual(result['remote_providers'], ('remote',))

    def test_private_paths_never_reach_unaware_tools_and_cancel_stops_callbacks(self):
        calls = []
        def tool(private):
            return NS(contribution=NS(supports_private_folders=private,
                is_available=lambda entry: calls.append(private) or True,
                create_widget=None, get_actions=lambda entry: ['action']))
        controller = FolderController()
        entry = FolderEntry('Private', local=NS(private=True, connection=NS(context='saved.conf')))
        controller.select_detail(entry, [tool(False), tool(True)], scope='local', unlock_target=lambda entry: None)
        request = controller.start_detail()
        self.assertEqual(len(request.detect(None, Event().is_set)), 1)
        self.assertEqual(calls, [True])
        calls.clear()
        cancelled = Event()
        cancelled.set()
        with self.assertRaises(OperationCancelled):
            request.detect(None, cancelled.is_set)
        self.assertEqual(calls, [])
