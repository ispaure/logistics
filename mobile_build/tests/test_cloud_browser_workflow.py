"""Listing ownership is testable without constructing the mobile application."""
import asyncio
from contextlib import asynccontextmanager, nullcontext
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

from features.rclone.mobile.browser_workflow import RemoteBrowserState, RemoteBrowserWorkflow


class BrowserWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setup_browser(self):
        @asynccontextmanager
        async def activity(stage):
            yield Mock()
        self.client = NS(generation=3, entries=Mock(return_value=[dict(path='book.pdf', directory=False)]))
        self.view = Mock()
        self.view.population_paused.side_effect = nullcontext
        self.view.activity.side_effect = activity
        self.view.busy.return_value = False
        self.view.selection.return_value = (['old'], 'old')
        self.view.current.side_effect = lambda client, generation: client is self.client and client.generation == generation
        self.state = RemoteBrowserState(path='old', remote='Files', rows={'old': {'path': 'old'}})
        return RemoteBrowserWorkflow(self.state, self.view)

    async def test_success_publishes_owned_state_before_recording_navigation(self):
        workflow = self.setup_browser()
        self.view.record.side_effect = lambda *args: self.assertEqual(self.state.path, 'new')
        self.assertTrue(await workflow.browse(self.client, 'Files', 'new'))
        self.client.entries.assert_called_once_with('Files', 'new')
        self.assertEqual(list(self.state.rows.values()), [dict(path='book.pdf', directory=False)])
        self.view.publish.assert_called_once()
        self.view.record.assert_called_once_with('Files', 'new')
        self.assertFalse(self.state.reading)
        self.view.set_busy.assert_called_with(False)

    async def test_network_failure_restores_prior_selection_and_rows(self):
        workflow = self.setup_browser()
        previous = self.state.rows
        self.client.entries.side_effect = OSError('offline')
        self.assertFalse(await workflow.browse(self.client, 'Files', 'new'))
        self.assertIs(self.state.rows, previous)
        self.view.location.assert_called_once_with('Files', 'old')
        self.view.labels.assert_called_with(['old'], 'old')
        self.view.publish.assert_not_called()

    async def test_retired_host_or_changed_credentials_cannot_publish_or_restore(self):
        for reason in ('retired', 'credentials'):
            with self.subTest(reason=reason):
                workflow = self.setup_browser()
                def entries(*args):
                    if reason == 'credentials':
                        self.client.generation += 1
                    else:
                        self.view.current.side_effect = None
                        self.view.current.return_value = False
                    return [dict(path='private.pdf', directory=False)]
                self.client.entries.side_effect = entries
                self.assertFalse(await workflow.browse(self.client, 'Files', 'new'))
                self.view.publish.assert_not_called()
                self.view.record.assert_not_called()
                self.view.stop.assert_called_once_with()
                self.assertEqual(self.state.rows, {})
                self.assertIsNone(self.state.remote)

    async def test_cancellation_releases_busy_state(self):
        workflow = self.setup_browser()
        self.client.entries.side_effect = asyncio.CancelledError
        with self.assertRaises(asyncio.CancelledError):
            await workflow.browse(self.client, 'Files', 'new')
        self.assertFalse(self.state.reading)
        self.view.set_busy.assert_called_with(False)
