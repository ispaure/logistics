"""Controlled row benchmarks reject contention instead of reporting noisy wins."""
from copy import deepcopy
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from commonUtils.testing.stages import TestStage
from mobile_build.validation import android_perf_load as load
from mobile_build.validation.notes_rows_performance_tools import compare, LoadObserver
from mobile_build.validation.document_storage_tools import run_android, BUNDLE

TEST_STAGE = TestStage.REGRESSION


def sample():
    return dict(owned_present=True, other_emulators=0, host_idle=.95, guest_idle=.90,
        guest_iowait=0, host_available_bytes=8 * 1024 ** 3,
        guest_available_bytes=512 * 1024 ** 2, swapout_delta=0, external_busy=.05, interval=1)


class ControlledLoadTests(unittest.TestCase):
    def test_guest_counter_parser_and_wrap_preserve_idle_ratios(self):
        self.assertEqual(load.proc_cpu('cpu  1 2 3 4 5 6 7 8 9 10\ncpu0 0'), (1, 2, 3, 4, 5, 6, 7, 8))
        self.assertEqual(load.cpu_idle((0, 0, 0, 0), (1, 1, 8, 0), idle_index=2), .8)
        self.assertEqual(load.cpu_idle((2 ** 32 - 2, 0), (2, 4), idle_index=1, bits=32), .5)
        self.assertIsNone(load.cpu_idle((1, 1), (1, 1), idle_index=1))
        with self.assertRaises(ValueError):
            load.cpu_idle((2, 1), (1, 1), idle_index=1)

    def test_start_requires_isolation_idle_memory_and_no_io_pressure(self):
        self.assertTrue(load.eligible(sample()))
        for key, value in dict(owned_present=False, other_emulators=1, host_idle=.8,
                guest_idle=.7, guest_iowait=.03, host_available_bytes=1,
                guest_available_bytes=1, swapout_delta=1).items():
            value_sample = sample()
            value_sample[key] = value
            self.assertFalse(load.eligible(value_sample), key)

    def test_window_allows_measured_app_work_but_rejects_external_contention(self):
        busy = sample()
        busy['guest_idle'] = 0
        self.assertTrue(load.window_verdict([busy])[0])
        for key, value in dict(other_emulators=1, owned_present=False, swapout_delta=1,
                               external_busy=.5, interval=0).items():
            invalid = sample()
            invalid[key] = value
            self.assertFalse(load.window_verdict([invalid])[0], key)
        self.assertFalse(load.window_verdict([])[0])

    def test_process_census_ignores_shell_text_and_retains_real_vm_identity(self):
        text = ('12 /sdk/emulator/qemu-system-aarch64-headless -avd owned-token -port 5554\n'
                '13 /bin/zsh -c emulator -avd text-only\n14 /sdk/emulator/emulator -avd other\n')
        with patch.object(load.subprocess, 'check_output', return_value=text):
            self.assertEqual(load.emulator_processes(), [dict(pid=12, avd='owned-token'), dict(pid=14, avd='other')])
        with patch.object(load.subprocess, 'check_output', return_value='1-02:03:04.5'):
            self.assertEqual(load.process_seconds(12), 93784.5)

    def test_probe_missing_adb_files_are_pending_state(self):
        observer = LoadObserver(['legacy', 'recycled'])
        observer.emulator = NS(adb='/adb', environment={})
        observer.record = dict(serial='emulator-5554')
        for code, value in ((0, b'cat: cache/missing.json: No such file'), (1, b'')):
            with patch('mobile_build.validation.notes_rows_performance_tools.subprocess.run',
                       return_value=NS(returncode=code, stdout=value)):
                self.assertIsNone(observer.read('missing.json'))

    def test_probe_deadline_rejects_invalid_values_before_build_or_device_creation(self):
        for value in (0, -1, 3601, True, '600'):
            with self.assertRaises(ValueError):
                run_android(None, None, None, None, None, bundle=BUNDLE, probe_timeout=value)

    def test_latency_targets_and_paired_sample_counts_are_enforced(self):
        rows = [dict(storage=s, cold=c, variant=v, first_draw_seconds=2 if v == 'legacy' else .1)
                for s in ('local', 'localcrypt') for c in (True, False) for v in ('legacy', 'recycled')]
        results = [dict(measurements=deepcopy(rows)) for _ in range(3)]
        self.assertEqual(len(compare(results)), 4)
        results[0]['measurements'][1]['first_draw_seconds'] = 1.1
        with self.assertRaises(AssertionError):
            compare(results)
        results[0]['measurements'][1]['first_draw_seconds'] = .1
        results[0]['measurements'].pop()
        with self.assertRaises(AssertionError):
            compare(results)
