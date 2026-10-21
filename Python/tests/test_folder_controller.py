"""Folder workers preserve cancellation, generation and private-path boundaries."""
from threading import Event
from types import SimpleNamespace as NS
import unittest
from commonUtils.runtime.operations import OperationCancelled
from ui_new.pages.folder_controller import FolderController


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
        work = controller.detail_work(NS(local=NS(private=True)), [tool(False), tool(True)])
        self.assertEqual(len(work(None, Event().is_set)[2]), 1)
        self.assertEqual(calls, [True])
        calls.clear()
        cancelled = Event()
        cancelled.set()
        with self.assertRaises(OperationCancelled):
            work(None, cancelled.is_set)
        self.assertEqual(calls, [])
