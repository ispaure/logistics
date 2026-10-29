"""Approval cannot outlive its reviewed files or credential binding."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from threading import Event
import unittest
from features.rclone.transfers.review import ReviewSession, ReviewRequest


class ReviewSessionTests(unittest.TestCase):
    request = ReviewRequest('Push', '/synthetic', 'Fixture:', 'fixture-binding')

    def finish(self, session):
        self.assertTrue(session.scan.retired.wait(2))
        return session.poll()

    def test_complete_approval_requires_second_scan_same_result_and_identity(self):
        revisions = iter(['one', 'two', 'two'])
        valid = [True]
        session = ReviewSession(self.request, lambda emit, cancel: next(revisions), lambda: valid[0])
        self.assertEqual(self.finish(session), 'ready')
        self.assertTrue(session.approve())
        self.assertEqual(self.finish(session), 'changed')
        self.assertFalse(session.approved)
        self.assertTrue(session.approve())
        self.assertEqual(self.finish(session), 'approved')
        valid[0] = False
        self.assertFalse(session.approved)

    def test_incomplete_requires_explicit_approval_and_retirement(self):
        started, release = Event(), Event()
        def scan(emit, cancel):
            started.set()
            release.wait(2)
            return 'revision'
        session = ReviewSession(self.request, scan)
        self.assertTrue(started.wait(2))
        self.assertFalse(session.approve())
        self.assertTrue(session.approve(incomplete=True))
        self.assertEqual(session.poll(), 'stopping')
        self.assertFalse(session.approved)
        release.set()
        self.assertEqual(self.finish(session), 'approved')

    def test_external_scan_cancellation_cannot_be_overridden_before_next_poll(self):
        for incomplete in (False, True):
            with self.subTest(incomplete=incomplete):
                session = ReviewSession(self.request, lambda emit, cancel: 'revision')
                self.assertEqual(self.finish(session), 'ready')
                session.scan.stop()
                self.assertFalse(session.approve(incomplete=incomplete))
                self.assertFalse(session.approved)
                self.assertEqual(session.state, 'cancelled')

    def test_cancel_and_failed_scan_never_authorize_execution(self):
        def scan(emit, cancel):
            raise ValueError('synthetic failure')
        session = ReviewSession(self.request, scan)
        self.assertEqual(self.finish(session), 'failed')
        self.assertFalse(session.approve())
        session.cancel()
        self.assertEqual(self.finish(session), 'cancelled')
        self.assertFalse(session.approved)
