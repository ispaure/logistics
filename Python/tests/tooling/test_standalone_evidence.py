"""Prove standalone retention leaves reports and unrelated evidence available."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from build_manager.retention import durable_hold
from commonUtils.testing.stages import TestStage
from logistics_build import standalone_evidence as policy

TEST_STAGE = TestStage.REGRESSION


class StandaloneEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def evidence(self, name, *, age=15, log='ios-build.log'):
        folder = self.root / 'tmp/test-results' / name
        folder.mkdir(parents=True)
        report = folder / 'ios-result.json'
        report.write_text('{"success": true}')
        attachment = folder / log
        attachment.write_bytes(b'local diagnostics')
        stamp = time.time() - age * 86400
        os.utime(attachment, (stamp, stamp))
        return report, attachment

    def test_cleanup_respects_identity_age_holds_and_pins(self):
        report, old = self.evidence('old', log='recording.mov')
        recent_report, recent = self.evidence('recent', age=1)
        held_report, held = self.evidence('held')
        pinned_report, pinned = self.evidence('pinned')
        changed_report, changed = self.evidence('changed')
        revised_report, revised = self.evidence('new-report')
        _, unregistered = self.evidence('unregistered')
        for anchor, attachment in ((report, old), (recent_report, recent), (held_report, held),
                                   (pinned_report, pinned), (changed_report, changed), (revised_report, revised)):
            policy.register(self.root, anchor, [attachment])
        durable_hold(held.parent, 'active review')
        pinned.with_name(pinned.name + '.keep').touch()
        changed.write_bytes(b'replacement data')
        revised_report.write_text('{"success": true, "updated": true}')
        self.assertEqual(policy.prune(self.root), [str(old)])
        self.assertTrue(old.exists())
        self.assertEqual(policy.prune(self.root, apply=True, selections={recent}), [])
        self.assertEqual(policy.prune(self.root, apply=True, selections={old}), [str(old)])
        self.assertFalse(old.exists())
        self.assertTrue(all(p.exists() for p in (recent, held, pinned, changed, revised, unregistered, report)))
        self.assertEqual(policy.prune(self.root), [])

    def test_rejects_release_manager_and_linked_paths(self):
        for name in ('alpha-release', 'build-manager/finished-run', 'mobile-evidence/run'):
            report, attachment = self.evidence(name)
            with self.assertRaises(ValueError):
                policy.register(self.root, report, [attachment])
        report, attachment = self.evidence('planned')
        (report.parent / 'plan.json').touch()
        with self.assertRaises(ValueError):
            policy.register(self.root, report, [attachment])
        report, attachment = self.evidence('plain')
        alias = attachment.with_name('alias.log')
        alias.symlink_to(attachment)
        with self.assertRaises(ValueError):
            policy.register(self.root, report, [alias])
        with self.assertRaises(ValueError):
            policy.register(self.root, report, [report])

    def test_probe_registers_known_files_after_successful_cleanup(self):
        report, attachment = self.evidence('complete')
        unclassified = report.with_name('review.png')
        unclassified.touch()
        cleanup = report.with_name('ios-cleanup.json')
        cleanup.write_text('{"removed": false}')
        policy.register_mobile_probe(self.root, report.parent, 'ios')
        self.assertEqual(policy.prune(self.root), [])
        cleanup.write_text('{"removed": true}')
        policy.register_mobile_probe(self.root, report.parent, 'ios')
        self.assertEqual(policy.prune(self.root, apply=True), [str(attachment)])
        self.assertTrue(report.exists())
        self.assertTrue(cleanup.exists())
        self.assertTrue(unclassified.exists())
