"""PDF search transitions without a UI toolkit, worker or PDF decoder."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest

from features.pdf.search import Match, Results
from features.pdf.search_controller import PDFSearchController, SearchRequest


MATCHES = Results((Match(0, 'first'), Match(0, 'second'), Match(2, 'last')))


class PDFSearchControllerTests(unittest.TestCase):
    def setUp(self):
        self.controller = PDFSearchController()

    def test_normalized_query_reuses_results_and_wraps_both_directions(self):
        owner = self.controller
        owner.set_query('  a\n needle  ')
        request = owner.step(1)
        self.assertIsInstance(request, SearchRequest)
        self.assertEqual(request.query, 'a needle')
        self.assertTrue(owner.state.busy)
        self.assertFalse(owner.state.next_enabled)
        self.assertIsNone(owner.step(-1))
        self.assertEqual(owner.complete(request, MATCHES), MATCHES.matches[0])
        owner.set_query('a  needle')
        self.assertEqual(owner.step(-1), MATCHES.matches[2])
        self.assertIn('Match 3 of 3', owner.state.status)
        self.assertEqual(owner.step(1), MATCHES.matches[0])
        self.assertTrue(owner.state.previous_enabled)
        self.assertFalse(owner.state.busy)

    def test_first_previous_starts_at_last_match_and_no_matches_are_cached(self):
        owner = self.controller
        owner.set_query('needle')
        self.assertEqual(owner.complete(owner.step(-1), MATCHES), MATCHES.matches[-1])
        owner.set_query('absent')
        self.assertIsNone(owner.complete(owner.step(1), Results(())))
        self.assertIn('No matches', owner.state.status)
        self.assertIsNone(owner.step(1))
        self.assertFalse(owner.state.busy)

    def test_query_change_waits_for_retirement_and_rejects_old_success_or_error(self):
        for failure in (False, True):
            with self.subTest(failure=failure):
                owner = PDFSearchController()
                owner.set_query('first')
                old = owner.step(1)
                owner.set_query('second')
                self.assertTrue(old.cancelled.is_set())
                self.assertTrue(owner.state.busy)
                self.assertIsNone(owner.step(1))
                if failure:
                    owner.fail(old, RuntimeError('obsolete failure'))
                else:
                    self.assertIsNone(owner.complete(old, MATCHES))
                self.assertEqual(owner.state.status, '')
                self.assertFalse(owner.results.matches)
                current = owner.step(1)
                owner.fail(old, RuntimeError('duplicate old completion'))
                self.assertIsNone(owner.complete(old, MATCHES))
                self.assertTrue(owner.state.busy)
                self.assertEqual(owner.complete(current, MATCHES), MATCHES.matches[0])

    def test_failure_allows_retry_and_preserves_empty_exception_name(self):
        owner = self.controller
        owner.set_query('needle')
        owner.fail(owner.step(1), RuntimeError())
        self.assertEqual(owner.state.status, 'Cannot search PDF: RuntimeError')
        self.assertTrue(owner.state.next_enabled)
        self.assertIsInstance(owner.step(1), SearchRequest)

    def test_clear_and_dispose_retire_sensitive_state_and_reject_late_results(self):
        owner = self.controller
        owner.set_query('private query')
        request = owner.step(1)
        owner.set_query('')
        self.assertTrue(request.cancelled.is_set())
        self.assertEqual(owner.state.status, '')
        owner.complete(request, MATCHES)
        self.assertIsNone(owner.step(1))
        owner.set_query('another private query')
        request = owner.step(1)
        owner.dispose()
        self.assertTrue(request.cancelled.is_set())
        self.assertIsNone(owner.complete(request, MATCHES))
        owner.fail(request, RuntimeError('late'))
        owner.set_query('ignored')
        self.assertEqual(owner.state.query, '')
        self.assertEqual(owner.state.status, '')
        self.assertFalse(owner.results.matches)
        self.assertFalse(owner.state.next_enabled)
        self.assertIsNone(owner.step(1))

    def test_navigation_error_cannot_overwrite_new_query_or_disposed_state(self):
        owner = self.controller
        owner.set_query('needle')
        owner.complete(owner.step(1), MATCHES)
        revision = owner.revision
        owner.navigation_failed(revision, ValueError('page unavailable'))
        self.assertIn('page unavailable', owner.state.status)
        self.assertIsInstance(owner.step(1), SearchRequest)
        owner.set_query('new query')
        owner.navigation_failed(revision, ValueError('late navigation'))
        self.assertEqual(owner.state.status, '')
        owner.dispose()
        owner.navigation_failed(owner.revision, ValueError('closed'))
        self.assertEqual(owner.state.status, '')


if __name__ == '__main__':
    unittest.main()
