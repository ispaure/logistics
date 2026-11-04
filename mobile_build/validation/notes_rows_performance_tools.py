"""Controlled paired Notes row benchmarks on manager-owned disposable Android devices."""
import argparse
import hashlib
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import time

from build_manager.locking import workspace_lock
from build_manager.registry import config_directory
from logistics_build.build_retention import scratch, remove_tree
from logistics_build.build_snapshots import materialize
from mobile_build.deployment import manager_settings
from mobile_build.tools import stage
from mobile_build.validation import document_storage_tools as runner
from mobile_build.validation import android_perf_load as load
from mobile_build.validation.ui_tools import verify_native_diagnostics

BUNDLE = 'io.github.ispaure.logisticsnotebookqa'


class LoadObserver:
    def __init__(self, order):
        self.order = order
        self.previous = None
        self.samples = []
        self.stable = 0
        self.grants = {}
        self.decisions = {}

    def read(self, name):
        value = subprocess.run([str(self.emulator.adb), '-s', self.record['serial'], 'exec-out',
            'run-as', BUNDLE, 'cat', 'cache/' + name], env=self.emulator.environment,
            capture_output=True, timeout=15)
        try:
            return json.loads(value.stdout) if value.returncode == 0 else None
        except (ValueError, UnicodeError):
            return None

    def write(self, name, value):
        if not re.fullmatch(r'[a-z0-9.-]+', name):
            raise ValueError('Unsafe performance protocol filename')
        self.emulator.invoke('-s', self.record['serial'], 'shell', 'run-as', BUNDLE, 'mkdir', '-p', 'cache')
        subprocess.run([str(self.emulator.adb), '-s', self.record['serial'], 'shell', 'run-as', BUNDLE,
                        'tee', 'cache/' + name + '.tmp'], input=json.dumps(value).encode(),
                       env=self.emulator.environment, capture_output=True, check=True, timeout=15)
        self.emulator.invoke('-s', self.record['serial'], 'shell', 'run-as', BUNDLE,
                             'mv', 'cache/' + name + '.tmp', 'cache/' + name)

    def sample(self):
        memory = load.host_memory()
        guest = load.guest_stats(self.emulator.invoke('-s', self.record['serial'], 'shell', 'cat',
                                                      '/proc/stat', '/proc/meminfo', timeout=15))
        processes = load.emulator_processes()
        own = [p for p in processes if p['pid'] == self.record['pid'] and p['avd'] == self.record['name']]
        if len(own) != 1:
            raise RuntimeError('Owned emulator process identity is unavailable for controlled load capture')
        own_processes = [p for p in processes if p['avd'] == self.record['name']]
        process_cpu = sum(load.process_seconds(p['pid']) for p in own_processes)
        cpu, idle, bits = load.host_cpu()
        now = time.monotonic()
        previous = self.previous
        interval = now - previous['time'] if previous else 0
        host_idle = load.cpu_idle(previous['cpu'], cpu, idle_index=idle, bits=bits) if previous else None
        guest_idle = load.cpu_idle(previous['guest'], guest['cpu'], idle_index=3) if previous else None
        cpu_delta = max(0, process_cpu - previous['process_cpu']) if previous else 0
        sample = dict(time=now, utc=datetime.now(timezone.utc).isoformat(), interval=interval,
            host_idle=host_idle, guest_idle=guest_idle,
            guest_iowait=load.cpu_idle(previous['guest'], guest['cpu'], idle_index=4) if previous else None,
            external_busy=load.normalized_external_busy(host_idle, cpu_delta, interval),
            host_available_bytes=memory['available_bytes'], guest_available_bytes=guest['available_bytes'],
            swapout_delta=max(0, memory['swapouts'] - previous['swapouts']) if previous else 0,
            owned_present=True, other_emulators=len({p['avd'] for p in processes if p['avd'] != self.record['name']}),
            emulator_pids=[p['pid'] for p in processes])
        self.previous = dict(time=now, cpu=cpu, guest=guest['cpu'], process_cpu=process_cpu,
                             swapouts=memory['swapouts'])
        self.samples.append(sample)
        self.stable = self.stable + 1 if load.eligible(sample) else 0
        with (self.output / 'load-samples.jsonl').open('a') as stream:
            stream.write(json.dumps(sample) + '\n')
        return sample

    def save(self):
        (self.output / 'load-windows.json').write_text(json.dumps(dict(grants=self.grants,
            decisions=self.decisions, policy=dict(stable_intervals=5, host_idle_min=.85, guest_idle_min=.75,
                external_host_busy_max=.20, host_available_min=4 * 1024 ** 3,
                guest_available_min=256 * 1024 ** 2, guest_iowait_max=.02, other_emulators=0, swapouts=0)), indent=2))

    def __call__(self, phase, emulator, record, output):
        self.emulator, self.record, self.output = emulator, record, output
        if phase == 'ready':
            if not record.get('token'):
                raise ValueError('Controlled benchmarks require an owned disposable emulator')
            emulator.verify(record)
            serial = record['serial']
            emulator.invoke('-s', serial, 'shell', 'settings', 'put', 'global', 'airplane_mode_on', '1')
            emulator.invoke('-s', serial, 'shell', 'am', 'broadcast', '-a', 'android.intent.action.AIRPLANE_MODE',
                             '--ez', 'state', 'true')
            emulator.invoke('-s', serial, 'shell', 'svc', 'wifi', 'disable')
            emulator.invoke('-s', serial, 'shell', 'svc', 'data', 'disable')
            for key in ('window_animation_scale', 'transition_animation_scale', 'animator_duration_scale'):
                emulator.invoke('-s', serial, 'shell', 'settings', 'put', 'global', key, '0')
            (output / 'controlled-environment.json').write_text(json.dumps(dict(offline=True,
                animations=False, order=self.order), indent=2))
        elif phase == 'installed':
            self.write('notes-performance-config.json', dict(order=self.order))
        elif phase == 'poll':
            if self.previous is None or time.monotonic() - self.previous['time'] >= .75:
                self.sample()
            request = self.read('notes-performance-progress.json')
            if not request or request.get('phase') != 'waiting':
                return
            nonce = request.get('nonce', '')
            if not re.fullmatch(r'[0-9a-f]{32}', nonce):
                raise ValueError('Unexpected performance window nonce')
            completed = self.read('notes-performance-window.json')
            if nonce in self.grants and nonce not in self.decisions and completed and completed.get('nonce') == nonce:
                self.sample()
                samples = self.samples[self.grants[nonce]['sample_index']:]
                accepted, reason = load.window_verdict(samples)
                decision = dict(nonce=nonce, accepted=accepted, reason=reason, measurement=completed,
                                sample_end_index=len(self.samples))
                self.decisions[nonce] = decision
                self.write('notes-performance-decision-' + nonce + '.json', decision)
                self.stable = 0
                self.save()
            elif nonce not in self.grants and self.stable >= 5:
                grant = dict(nonce=nonce, eligible=True, label=request['label'], sample_index=len(self.samples),
                             stable_samples=self.samples[-5:])
                self.grants[nonce] = grant
                self.write('notes-performance-go-' + nonce + '.json', grant)
                self.save()
        elif phase == 'result':
            self.save()


def compare(results):
    summary = {}
    for storage in ('local', 'localcrypt'):
        for cold in (True, False):
            values = {variant: [x['first_draw_seconds'] for r in results for x in r['measurements']
                               if x['storage'] == storage and x['cold'] == cold and x['variant'] == variant]
                      for variant in ('legacy', 'recycled')}
            assert len(values['legacy']) == len(values['recycled']) == len(results)
            assert all(math.isfinite(x) and x > 0 for group in values.values() for x in group)
            baseline, optimized = (statistics.median(values[v]) for v in ('legacy', 'recycled'))
            limit = 1.0 if cold else .5
            summary[storage + ('_cold' if cold else '_repeated')] = dict(samples=values,
                baseline_median=baseline, optimized_median=optimized,
                speedup=baseline / optimized, limit_seconds=limit)
            if max(values['recycled']) > limit or optimized > baseline / 4:
                raise AssertionError('Notes row performance target missed: ' + json.dumps(summary))
    return summary


def wait_isolation(timeout):
    deadline = time.monotonic() + timeout
    while load.emulator_processes():
        if time.monotonic() >= deadline:
            raise TimeoutError('No isolated Android emulator window became available; no other device was altered')
        print('Waiting for other emulator owners to finish before creating a disposable device', flush=True)
        time.sleep(30)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--isolation-timeout', type=int, default=1800)
    args = parser.parse_args()
    if not 1 <= args.runs <= 6 or not 1 <= args.isolation_timeout <= 3600:
        parser.error('Use 1–6 runs and a bounded isolation timeout up to 3600 seconds')
    root = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    host_sources = {}
    for name in ('notes_rows_performance_tools.py', 'android_perf_load.py', 'document_storage_tools.py'):
        path = Path(__file__).with_name(name)
        committed = subprocess.check_output(['git', '-C', str(root), 'show',
            'HEAD:mobile_build/validation/' + name])
        host_sources[name] = dict(working_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                  committed_sha256=hashlib.sha256(committed).hexdigest())
    (output / 'host-source-hashes.json').write_text(json.dumps(host_sources, indent=2))
    options, _ = manager_settings.settings(root / 'mobile_build')
    results = []
    workspace = None
    try:
        with workspace_lock(config_directory() / 'locks/android-performance.lock', timeout=3600):
            wait_isolation(args.isolation_timeout)
            with scratch(root) as workspace:
                source = workspace / 'source'
                commit = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
                materialize(root, source, commit)
                payload = workspace / 'payload'
                manifest = stage(source, payload)
                (output / 'source.json').write_text(json.dumps(manifest, indent=2))
                env = dict(os.environ, ANDROID_HOME=options['tools.android_sdk'], ANDROID_SDK_ROOT=options['tools.android_sdk'],
                    JAVA_HOME=options['tools.java'], LOGISTICS_DEPLOY_WORKSPACE=str(workspace),
                    XDG_CACHE_HOME=str(workspace / 'probe-tools'))
                env['PATH'] = str(root / 'mobile_build/.tools/go/bin') + os.pathsep + env['PATH']
                os.environ.update(env)
                runner.SOURCE = source
                runner.android()
                project = workspace / 'build/logisticsmobile/android/gradle'
                shutil.copytree(root / 'mobile_build/build/logisticsmobile/android/gradle', project,
                                ignore=shutil.ignore_patterns('build', '.gradle', '__pycache__'))
                with (project / 'app/build.gradle').open('a') as stream:
                    stream.write('\nandroid.sourceSets.main.java.srcDir(' + json.dumps(str(
                        source / 'mobile_build/native_tests/android/notes_rows')) + ')\n')
                for index in range(args.runs):
                    wait_isolation(args.isolation_timeout)
                    run_output = output / f'run-{index + 1}'
                    run_output.mkdir()
                    observer = LoadObserver(['legacy', 'recycled'] if index % 2 == 0 else ['recycled', 'legacy'])
                    arguments = dict(bundle=BUNDLE, entry_point='tests.logisticsmobile.notes_rows_performance_probe',
                        result_name='notes-rows-performance-result.json', reuse_project=True,
                        observe=observer, probe_timeout=1800)
                    if index == 0:
                        result = runner.run_android(workspace, payload, run_output, env, options, **arguments)
                    else:
                        result = runner.exercise_android_app(project / 'app/build/outputs/apk/debug/app-debug.apk',
                            workspace, run_output, env, options, **arguments)
                    verify_native_diagnostics(run_output / 'android-logcat.txt')
                    assert json.loads((run_output / 'android-cleanup.json').read_text())['removed']
                    assert all(observer.decisions[x['nonce']]['accepted'] for x in result['measurements'])
                    results.append(result)
                    print('Controlled Notes row run completed: ' + str(index + 1), flush=True)
                apk_hashes = {json.loads((output / f'run-{i + 1}/android-apk.json').read_text())['sha256']
                              for i in range(args.runs)}
                assert len(apk_hashes) == 1, 'Paired devices did not execute identical APK bytes'
                summary = compare(results)
                (output / 'summary.json').write_text(json.dumps(dict(success=True, source=manifest,
                    runs=args.runs, apk_sha256=next(iter(apk_hashes)), comparison=summary), indent=2))
                remove_tree(payload, ownership_files=())
    finally:
        (output / 'workspace-cleanup.json').write_text(json.dumps(dict(workspace=str(workspace),
            removed=workspace is not None and not workspace.exists())))


if __name__ == '__main__':
    main()
