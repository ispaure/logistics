"""Explicit diagnostic-only full native suite; never supplies release acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import shutil
import signal
import stat
import subprocess
import time
from uuid import uuid4
import zipfile

BASE_SOURCE = '43a4591ae41694747ba2af73b4ee18ff2b66fa4f'
BASE_BINARY = '96000147ec8193037449ae904a40ea228089f31554fe197dfb4d7ad05b941007'
BASE_SHARED = '4d7c0e7547eef5dfc6d06708c1fb9e04b064a71f'
BASE_FINGERPRINT = '6d81d272c85f97334b43a0aaa3d745ad808631b4f0ef22aadae6679c91963180'
BUNDLE = 'io.github.ispaure.logisticsmobile'
MODEL = 'com.apple.CoreSimulator.SimDeviceType.iPad-Pro-13-inch-M5-16GB'
RUNTIME = 'com.apple.CoreSimulator.SimRuntime.iOS-27-0'
MAX_ALLOCATOR = 8 * 1024 ** 3
MIN_SCRATCH_FREE = 12 * 1024 ** 3
MAX_TRUNCATED_CAPTURE = 64 * 1024 ** 2
MAX_GROWTH_SAMPLES = 1024
MIN_DISK_RESERVE = 512 * 1024 ** 2
MAX_TRACE = 64 * 1024 ** 2


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def safe_archive(path, destination):
    destination = Path(destination).resolve()
    if path.stat().st_size > 150 * 1024 ** 2:
        raise ValueError('Diagnostic app archive exceeds its size budget.')
    with zipfile.ZipFile(path) as archive:
        if sum(item.file_size for item in archive.infolist()) > 1500 * 1024 ** 2:
            raise ValueError('Expanded diagnostic app exceeds its size budget.')
        for item in archive.infolist():
            name = PurePosixPath(item.filename)
            if name.is_absolute() or '..' in name.parts:
                raise ValueError('Unsafe diagnostic archive path.')
            if stat.S_ISLNK(item.external_attr >> 16):
                target = destination / Path(item.filename).parent / archive.read(item).decode()
                if not target.resolve().is_relative_to(destination):
                    raise ValueError('Diagnostic archive link escapes extraction root.')


def compare_python(expected, actual):
    files = {path.relative_to(expected): path for path in Path(expected).rglob('*.py')}
    for relative, path in files.items():
        other = Path(actual) / relative
        if not other.is_file() or other.is_symlink() or path.read_bytes() != other.read_bytes():
            raise ValueError('Original diagnostic source mismatch: ' + str(relative))
    return len(files)


def verify_app(app, payload, fixtures):
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    source = json.loads((app / 'app/mobile/source.json').read_text())
    expected = json.loads((payload / 'source.json').read_text())
    if (info.get('MainModule') != 'tests.logisticsmobile' or source != expected
            or digest(app / 'Logistics Mobile') != BASE_BINARY
            or source.get('dirty') is not False or source.get('commonUtils_dirty') is not False
            or source.get('logistics_commit') != BASE_SOURCE or source.get('commonUtils_commit') != BASE_SHARED
            or source.get('source_sha256') != BASE_FINGERPRINT):
        raise ValueError('Original 43a diagnostic application identity differs.')
    native_fixture = app / 'app/tests/logisticsmobile'
    if not native_fixture.is_dir():
        native_fixture = app / 'app_packages/tests/logisticsmobile'
    counts = dict(product_python=compare_python(payload, app / 'app'),
                  fixture_python=compare_python(fixtures, native_fixture))
    actual = {path.relative_to(native_fixture) for path in native_fixture.rglob('*.py')}
    expected_members = {path.relative_to(fixtures) for path in fixtures.rglob('*.py')}
    if actual != expected_members:
        raise ValueError('Original native fixture membership differs.')
    return source, native_fixture, counts


def compile_command(source, output, sdk):
    return ['xcrun', '--sdk', 'iphonesimulator', 'clang', '-arch', 'arm64', '-isysroot', str(sdk),
            '-mios-simulator-version-min=15.0', '-dynamiclib', '-fno-objc-arc', '-fvisibility=hidden',
            '-Wall', '-Wextra', '-Werror', '-framework', 'UIKit', '-lobjc', str(source), '-o', str(output)]


def launch_environment(app, container):
    app, container = Path(app).resolve(), Path(container).resolve()
    cache = container / 'Library/Caches'
    allocator = cache / 'diagnostic-allocator'
    allocator.mkdir(parents=True, mode=0o700, exist_ok=False)
    trace = cache / 'diagnostic-view-dealloc.trace'
    descriptor = os.open(trace, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    environment = dict(os.environ)
    for key in ('NSZombieEnabled', 'MallocStackLogging', 'MallocStackLoggingNoCompact',
                'MallocStackLoggingDirectory', 'DYLD_INSERT_LIBRARIES'):
        environment.pop(key, None)
        environment.pop('SIMCTL_CHILD_' + key, None)
    environment.update(SIMCTL_CHILD_MallocStackLoggingNoCompact='1',
        SIMCTL_CHILD_MallocStackLoggingDirectory=str(allocator),
        SIMCTL_CHILD_LOGISTICS_DEALLOC_TRACE_PATH=str(trace),
        SIMCTL_CHILD_DYLD_INSERT_LIBRARIES=str(app / 'Frameworks/LogisticsViewLifetime.dylib'))
    return environment, cache, trace, allocator


def trace_installed(path, pid):
    with path.open(errors='replace') as stream:
        text = stream.read(16384)
    records = []
    for line in text.splitlines():
        fields = line.split(' ', 6)
        if len(fields) != 7:
            continue
        try:
            if int(fields[1], 16) == pid:
                records.append((fields[0], fields[6]))
        except ValueError:
            continue
    return (('I', 'UIView.dealloc-installed-v1') in records and ('N', '1') in records
            and ('G', '') in records and not any(kind == 'F' for kind, _ in records))


def allocator_size(directory):
    return sum(path.stat().st_size for path in directory.rglob('*') if path.is_file())



class AllocatorFiles:
    """Bounded read-only inode handles, durable growth and honest partial capture."""
    def __init__(self, growth_path=None, *, scratch_path=None, clock=time.monotonic):
        self.files, self.samples, self.pending_files = {}, [], []
        self.growth_path, self.clock = growth_path, clock
        self.started = clock()
        self.scratch_path, self.directory = scratch_path, None
        self.latest = None
        self.stop_reason = None

    @staticmethod
    def metadata(info, name):
        blocks = getattr(info, 'st_blocks', None)
        return dict(original_name=name, device=info.st_dev, inode=info.st_ino,
                    logical_bytes=info.st_size, st_blocks=blocks,
                    allocated_bytes=blocks * 512 if blocks is not None else None)

    def persist_sample(self, pending=None):
        if pending is not None:
            self.pending_files = [dict(row, unopened=True) for row in pending]
        pending = self.pending_files
        files = [self.metadata(os.fstat(descriptor), name) for descriptor, name in self.files.values()]
        files.extend(pending)
        logical = sum(row['logical_bytes'] for row in files)
        allocated = (sum(row['allocated_bytes'] for row in files)
                     if all(row['allocated_bytes'] is not None for row in files) else None)
        now = self.clock()
        scratch = self.scratch_path or self.directory
        output = Path(self.growth_path).parent if self.growth_path is not None else self.directory
        scratch_free = shutil.disk_usage(scratch).free
        output_free = shutil.disk_usage(output).free
        sample = dict(scratch_free_bytes=scratch_free, output_free_bytes=output_free,
                      disk_reserve_bytes=MIN_DISK_RESERVE, captured_ns=time.time_ns(), monotonic_s=now, elapsed_s=now - self.started,
                      logical_bytes=logical, allocated_bytes=allocated,
                      st_blocks=sum(row['st_blocks'] for row in files)
                      if all(row['st_blocks'] is not None for row in files) else None,
                      file_count=len(files), file_count_is_lower_bound=bool(pending),
                      open_fds=len(self.files))
        self.latest = dict(sample, files=files)
        self.samples.append(sample)
        self.samples = self.samples[-MAX_GROWTH_SAMPLES:]
        if self.growth_path is not None:
            save(self.growth_path, dict(schema=1, diagnostic_only=True, logical_budget=MAX_ALLOCATOR,
                 max_samples=MAX_GROWTH_SAMPLES, samples=self.samples, latest=self.latest,
                 note='st_size is logical file length; st_blocks*512 measures allocated filesystem bytes, not RAM.'))
        return logical

    def observe(self, directory):
        self.directory = Path(directory)
        for path in directory.rglob('*'):
            if path.is_symlink():
                raise ValueError('Allocator evidence must not contain links.')
            if not path.is_file():
                continue
            info = path.stat()
            key = (info.st_dev, info.st_ino)
            if key in self.files:
                continue
            if len(self.files) >= 128:
                self.persist_sample([self.metadata(info, path.relative_to(directory).as_posix())])
                self.stop_reason = 'allocator-fd-limit'
                raise ValueError('Too many allocator evidence files; sample includes at least 129 files.')
            descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != key:
                os.close(descriptor)
                raise ValueError('Allocator evidence changed while opening.')
            self.files[key] = (descriptor, path.relative_to(directory).as_posix())
        # Persist first: even the sample that rejects the run remains evidence.
        logical = self.persist_sample()
        if min(self.latest['scratch_free_bytes'], self.latest['output_free_bytes']) < MIN_DISK_RESERVE:
            self.stop_reason = 'disk-reserve'
            raise ValueError('Diagnostic disk reserve fell below 512 MiB; retained rejecting growth sample.')
        if logical > MAX_ALLOCATOR:
            self.stop_reason = 'allocator-logical-budget'
            raise ValueError('Allocator evidence exceeded its 8 GiB logical budget.')
        return logical

    def capture(self, output):
        output.mkdir(parents=True, exist_ok=True)
        logical = self.persist_sample()
        free = shutil.disk_usage(output).free
        reason = self.stop_reason
        if logical > MAX_ALLOCATOR:
            reason = reason or 'allocator-logical-budget'
        if free < logical + MAX_TRUNCATED_CAPTURE:
            reason = reason or 'insufficient-free-space-for-complete-copy'
        if not self.files:
            reason = reason or 'no-allocator-files-observed'
        partial = reason is not None
        remaining_budget = min(MAX_TRUNCATED_CAPTURE, max(0, free - 1024 * 1024)) if partial else logical
        records = []
        for index, ((device, inode), (descriptor, name)) in enumerate(self.files.items()):
            info = os.fstat(descriptor)
            size = info.st_size
            amount = min(size, remaining_budget)
            remaining_budget -= amount
            truncated = amount < size
            target = output / ('inode-' + str(index) + ('.TRUNCATED' if truncated else '')) if amount else None
            if target is not None:
                os.lseek(descriptor, 0, os.SEEK_SET)
                with target.open('wb') as stream:
                    remaining = amount
                    while remaining:
                        block = os.read(descriptor, min(1024 * 1024, remaining))
                        if not block:
                            raise ValueError('Allocator evidence ended before its recorded size.')
                        stream.write(block)
                        remaining -= len(block)
            after = os.fstat(descriptor)
            changed = after.st_size != size or after.st_mtime_ns != info.st_mtime_ns
            truncated = truncated or changed
            if changed and target is not None and not target.name.endswith('.TRUNCATED'):
                renamed = target.with_name(target.name + '.TRUNCATED')
                target.rename(renamed)
                target = renamed
            records.append(dict(self.metadata(info, name), bytes=size, captured_bytes=amount,
                source_logical_bytes_after=after.st_size, source_changed_during_capture=changed,
                truncated=truncated, complete=not truncated, retained_file=target.name if target else None,
                sha256=digest(target) if target else None))
        if not reason and any(row['truncated'] for row in records):
            reason = 'allocator-grew-during-capture'
        save(output / 'index.json', records)
        save(output / 'capture-metadata.json', dict(schema=1, diagnostic_only=True,
            complete=not partial and all(row['complete'] for row in records),
            history_incomplete=partial or any(row['truncated'] for row in records), reason=reason,
            source_logical_bytes=logical, source_allocated_bytes=self.latest['allocated_bytes'],
            captured_bytes=sum(row['captured_bytes'] for row in records), capture_free_bytes=free,
            prefix_budget=MAX_TRUNCATED_CAPTURE if partial else None, logical_budget=MAX_ALLOCATOR,
            atomic_allocator_snapshot=False,
            unopened_files=self.pending_files,
            completeness_scope='Observed file lengths copied; live in-place writes cannot be proven absent.'))
        return records

    def close(self):
        failure = None
        for descriptor, _ in self.files.values():
            try:
                os.close(descriptor)
            except OSError as error:
                failure = error
        self.files.clear()
        if failure is not None:
            raise failure



def summarize_trace(path):
    """Bounded unmatched entries are candidates, not a root-cause verdict."""
    active, invalid, truncated = {}, 0, False
    remaining = MAX_TRACE
    with path.open('rb') as stream:
        while remaining > 0:
            raw = stream.readline(min(512, remaining))
            if not raw:
                break
            remaining -= len(raw)
            if not raw.endswith(b'\n'):
                invalid += 1
                truncated = True
                break
            line = raw.decode('utf-8', errors='replace')
            if line.startswith('T '):
                truncated = True
                continue
            fields = line.rstrip('\n').split(' ', 6)
            if len(fields) != 7 or fields[0] not in {'E', 'C', 'X'}:
                continue
            kind, pid, address, thread, seconds, nanos, name = fields
            try:
                for field in (pid, address, thread, seconds, nanos):
                    int(field, 16)
            except ValueError:
                invalid += 1
                continue
            stack = active.setdefault((pid, thread), [])
            if kind == 'E':
                stack.append(dict(pid=pid, pointer=address, thread=thread, seconds=seconds, nanoseconds=nanos))
            elif not stack or stack[-1]['pointer'] != address:
                invalid += 1
            elif kind == 'C':
                stack[-1]['class_name'] = name
            else:
                stack.pop()
        if remaining == 0 and stream.read(1):
            truncated = True
    return dict(diagnostic_only=True, truncated=truncated, mismatched_records=invalid,
                unmatched_candidates=[row for stack in active.values() for row in stack],
                limitation='Correlate candidates with the actual faulting thread and stack; abrupt exit alone can leave unmatched entries.')


def summary(receipt):
    actual = receipt.get('original_suite_result') or {}
    return dict(diagnostic_only=True, status=receipt.get('status'),
                original_suite_success=actual.get('success'), completed_cases=len(actual.get('cases', [])),
                expected_cases=len(actual.get('expected_cases', [])), original_error=actual.get('error'),
                capture_errors=receipt.get('capture_errors', []), cleanup=receipt.get('cleanup'),
                allocator_history_complete=(receipt.get('allocator_capture') or {}).get('complete'),
                allocator_capture_reason=(receipt.get('allocator_capture') or {}).get('reason'),
                release_acceptance=False)


def collect(cache, output, client, device, pid, started, allocator_files=None):
    """Read existing evidence while its owned simulator still exists; no launch."""
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    if allocator_files is not None:
        try:
            allocator_files.capture(output / 'retained-allocator-inodes')
        except (OSError, ValueError) as error:
            errors.append('allocator capture: ' + type(error).__name__)
    for pattern in ('diagnostic-*', 'logistics-native-ui-*'):
        for path in cache.glob(pattern):
            if path.name == 'diagnostic-allocator' and allocator_files is not None:
                continue  # Inode records retain names without duplicating log bytes.
            try:
                if path.is_dir():
                    shutil.copytree(path, output / path.name, dirs_exist_ok=True)
                else:
                    shutil.copyfile(path, output / path.name)
            except OSError as error:
                errors.append(type(error).__name__ + ': ' + path.name)
    trace = output / 'diagnostic-view-dealloc.trace'
    if trace.exists():
        try:
            save(output / 'view-dealloc-summary.json', summarize_trace(trace))
        except (OSError, ValueError) as error:
            errors.append('trace summary: ' + type(error).__name__)
    from build_manager.native_commands import command
    for name, arguments in (
            ('simulator-system.log', ['show', '--last', '35m', '--style', 'compact', '--predicate',
                'process == "Logistics Mobile"']),
            ('simulator-logarchive.txt', ['collect', '--last', '35m', '--output', str(output / 'simulator.logarchive')])):
        try:
            with (output / name).open('w') as stream:
                code = command(['xcrun', 'simctl', 'spawn', device, 'log', *arguments], output,
                               90, stdout=stream, stderr=subprocess.STDOUT, check=False)
            if code:
                errors.append(name + ': exit ' + str(code))
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            errors.append(name + ': ' + type(error).__name__)
    for path in (Path.home() / 'Library/Logs/DiagnosticReports').glob('*.ips'):
        if path.stat().st_mtime < started or path.stat().st_size > 10 * 1024 ** 2:
            continue
        try:
            data = json.loads('\n'.join(path.read_text().splitlines()[1:]))
            if data.get('pid') == pid or data.get('procPid') == pid:
                shutil.copyfile(path, output / path.name)
        except (OSError, ValueError):
            continue
    return errors


def finish(cache, output, client, device, name, pid, started, receipt, allocator_files=None):
    # Ordering is the contract: capture first, teardown second, persist outcome.
    try:
        receipt['capture_errors'] = collect(cache, output, client, device, pid, started, allocator_files)
        metadata = output / 'retained-allocator-inodes/capture-metadata.json'
        if metadata.exists():
            receipt['allocator_capture'] = json.loads(metadata.read_text())
    except BaseException as error:
        receipt['capture_errors'] = [type(error).__name__]
    finally:
        if allocator_files is not None:
            try:
                allocator_files.close()
            except OSError as error:
                receipt.setdefault('capture_errors', []).append('allocator close: ' + type(error).__name__)
        try:
            client.remove(device, name)
            receipt['cleanup'] = 'verified-removed' if client.matching(device, name) is None else 'unverified'
            if receipt['cleanup'] == 'verified-removed':
                save(output / 'owned-device.json', dict(device=device, name=name, removed=True))
        except BaseException as error:
            receipt['cleanup'] = 'failed'
            receipt['cleanup_error'] = str(error)
        save(output / 'diagnostic-receipt.json', receipt)
        save(output / 'diagnostic-summary.json', summary(receipt))
        print(json.dumps(summary(receipt)), flush=True)




def require_scratch_space(workspace, output, receipt):
    metadata = dict(checked_ns=time.time_ns(), filesystem_path=str(workspace),
                    free_bytes=shutil.disk_usage(workspace).free, minimum_free_bytes=MIN_SCRATCH_FREE)
    receipt['disk_preflight'] = metadata
    save(output / 'disk-preflight.json', metadata)
    save(output / 'diagnostic-receipt.json', receipt)
    if metadata['free_bytes'] < MIN_SCRATCH_FREE:
        raise RuntimeError('Diagnostic scratch filesystem requires at least 12 GiB free before preparation.')
    return metadata


def verify_source_run(run_info):
    if run_info.get('head_sha') != BASE_SOURCE:
        raise ValueError('Artifact run is not the original 43a source.')
    # Reusable mobile-build jobs publish artifacts on their caller's run.
    if run_info.get('path') not in {'.github/workflows/mobile-build.yml', '.github/workflows/release.yml'}:
        raise ValueError('Original artifact run has an unreviewed workflow owner.')


def run(args):
    from build_manager.apple_simulators import AppleSimulators
    from build_manager.native_commands import command, interrupt
    from build_manager.github import GitHub
    from logistics_build.build_retention import scratch
    from mobile_build import tools
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupt)
    root, baseline, output = args.root.resolve(), args.baseline.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    client = AppleSimulators()
    github = GitHub('ispaure/logistics', os.environ['GITHUB_TOKEN'])
    run_info = github.request('GET', github.base + '/actions/runs/' + str(args.source_run))
    verify_source_run(run_info)
    if subprocess.check_output(['git', '-C', str(baseline), 'rev-parse', 'HEAD'], text=True).strip() != BASE_SOURCE:
        raise ValueError('Pristine source baseline must be exactly 43a.')
    receipt = dict(schema=1, diagnostic_only=True, status='preparing', source_run=args.source_run,
                   original_source=BASE_SOURCE, original_shared=BASE_SHARED,
                   original_workflow=run_info['path'], original_workflow_id=run_info.get('workflow_id'))
    device = None
    with scratch(root) as work:
        require_scratch_space(work, output, receipt)
        archive, = args.artifact.glob('**/Logistics-ios-simulator.zip')
        safe_archive(archive, work / 'extracted')
        command(['ditto', '-x', '-k', str(archive), str(work / 'extracted')], root, 90)
        app, = (work / 'extracted').glob('*.app')
        payload = work / 'expected'
        tools.stage(baseline, payload, allow_dirty=False)
        source, fixture, counts = verify_app(app, payload, baseline / 'mobile_build/native_tests/tests/logisticsmobile')
        native = root / 'mobile_build/native_tests/diagnostics'
        receipt.update(original_manifest=source, verified_files=counts,
            original_archive_sha256=digest(archive), original_binary_sha256=digest(app / 'Logistics Mobile'),
            c_source_sha256=digest(native / 'UIViewLifetime.m'), entry_sha256=digest(native / 'ipad_lifetimes_entry.py'),
            diagnostic_commit=subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip())
        frameworks = app / 'Frameworks'
        frameworks.mkdir(exist_ok=True)
        dylib = frameworks / 'LogisticsViewLifetime.dylib'
        sdk = subprocess.check_output(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path'], text=True).strip()
        compilation = compile_command(native / 'UIViewLifetime.m', dylib, sdk)
        receipt['compile_argv'] = compilation
        command(compilation, root, 120)
        shutil.copyfile(native / 'ipad_lifetimes_entry.py', fixture / 'ipad_lifetimes_entry.py')
        info = plistlib.loads((app / 'Info.plist').read_bytes())
        info['MainModule'] = 'tests.logisticsmobile.ipad_lifetimes_entry'
        (app / 'Info.plist').write_bytes(plistlib.dumps(info))
        for target in (dylib, app):
            command(['codesign', '--force', '--sign', '-', str(target)], root, 45)
        receipt.update(diagnostic_binary_sha256=digest(app / 'Logistics Mobile'), dylib_sha256=digest(dylib))
        cache = None
        allocator_files = AllocatorFiles(output / 'allocator-growth.json', scratch_path=work)
        name = 'Build Manager diagnostic iPad ' + uuid4().hex
        started, pid = time.time(), None
        try:
            device = client.create(name, MODEL, RUNTIME)
            save(output / 'owned-device.json', dict(device=device, name=name))
            receipt.update(device=device, model=MODEL, runtime=RUNTIME)
            client.boot(device)
            client.invoke('install', device, str(app), timeout=90)
            installed = Path(client.invoke('get_app_container', device, BUNDLE, 'app'))
            container = Path(client.invoke('get_app_container', device, BUNDLE, 'data'))
            environment, cache, trace, allocator = launch_environment(installed, container)
            launched = subprocess.run(['xcrun', 'simctl', 'launch', '--stdout=' + str(output / 'launch.stdout'),
                '--stderr=' + str(output / 'launch.stderr'), device, BUNDLE], env=environment,
                text=True, capture_output=True, timeout=45, check=True)
            pid = int(launched.stdout.rsplit(':', 1)[1].strip())
            receipt['pid'] = pid
            receipt['status'] = 'running-original-full-suite'
            save(output / 'diagnostic-receipt.json', receipt)
            deadline, initial_deadline = time.monotonic() + 1800, time.monotonic() + 30
            observed_growth, previous = False, 0
            while time.monotonic() < deadline:
                current = allocator_files.observe(allocator)
                observed_growth = observed_growth or (previous > 0 and current > previous)
                previous = current
                receipt.update(allocator_bytes=current, allocator_files_growing=observed_growth,
                               hook_installed=trace_installed(trace, pid))
                if trace.stat().st_size > MAX_TRACE:
                    raise RuntimeError('Native trace exceeded its global 64 MiB diagnostic budget.')
                if time.monotonic() > initial_deadline and (not receipt['hook_installed'] or not observed_growth):
                    raise RuntimeError('Native hook or actual allocator history was not established.')
                result = cache / 'logistics-native-ui-result.json'
                fault = cache / 'logistics-native-ui-fault.log'
                if result.exists():
                    receipt.update(status='diagnostic-suite-returned', original_suite_result=json.loads(result.read_text()))
                    break
                if fault.exists() and 'Fatal Python error' in fault.read_text(errors='replace'):
                    receipt['status'] = 'diagnostic-native-crash'
                    break
                time.sleep(2)
            else:
                raise RuntimeError('Original complete native suite exceeded its diagnostic deadline.')
        except BaseException as error:
            if allocator_files.latest is not None:
                receipt.update(allocator_bytes=allocator_files.latest['logical_bytes'],
                    allocator_allocated_bytes=allocator_files.latest['allocated_bytes'],
                    allocator_file_count=allocator_files.latest['file_count'],
                    scratch_free_bytes=allocator_files.latest['scratch_free_bytes'],
                    output_free_bytes=allocator_files.latest['output_free_bytes'],
                    allocator_stop_reason=allocator_files.stop_reason)
            receipt.update(status='diagnostic-error', error=type(error).__name__ + ': ' + str(error))
            raise
        finally:
            if device is not None:
                finish(cache or work / 'missing-cache', output, client, device, name, pid, started, receipt, allocator_files)
                if receipt.get('cleanup') != 'verified-removed':
                    (work / '.keep').touch()
                    receipt['retained_workspace'] = str(work)
                    save(output / 'diagnostic-receipt.json', receipt)
            else:
                allocator_files.close()
                save(output / 'diagnostic-receipt.json', receipt)



def cleanup_saved(output):
    lease = Path(output) / 'owned-device.json'
    if not lease.exists():
        return
    row = json.loads(lease.read_text())
    if not row['name'].startswith('Build Manager diagnostic iPad '):
        raise ValueError('Refusing cleanup without diagnostic simulator ownership.')
    from build_manager.apple_simulators import AppleSimulators
    client = AppleSimulators()
    client.remove(row['device'], row['name'])
    if client.matching(row['device'], row['name']) is not None:
        raise RuntimeError('Diagnostic simulator remains after cleanup.')
    save(lease, dict(row, removed=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'baseline', 'artifact', 'output'):
        parser.add_argument('--' + name, type=Path, required=name == 'output')
    parser.add_argument('--source-run', type=int)
    parser.add_argument('--cleanup-only', action='store_true')
    args = parser.parse_args()
    if args.cleanup_only:
        cleanup_saved(args.output)
        return
    if not all((args.root, args.baseline, args.artifact, args.source_run)):
        parser.error('Execution requires root, baseline, artifact and source-run.')
    try:
        run(args)
    except BaseException as error:
        path = args.output / 'diagnostic-receipt.json'
        receipt = json.loads(path.read_text()) if path.exists() else dict(schema=1, diagnostic_only=True)
        receipt.update(status='diagnostic-error', error=type(error).__name__ + ': ' + str(error))
        save(path, receipt)
        raise


if __name__ == '__main__':
    main()
