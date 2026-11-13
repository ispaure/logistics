"""Opt-in scheduling for reviewed macOS offscreen file-stage processes."""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
import os
from pathlib import Path
import signal
import subprocess
import sys
from threading import Event
from time import monotonic
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
# Explicit files, rather than a directory glob: a newly added test starts
# exclusive until its resources and concurrent behavior have been reviewed.
QT_FILES = frozenset('Python/tests/version_control/' + name for name in (
    'test_git_backend.py', 'test_git_commands.py', 'test_git_diff_view.py',
    'test_git_hunk_layout.py', 'test_git_menu_retirement.py', 'test_git_merge.py',
    'test_git_models.py', 'test_git_preferences.py', 'test_git_repository_tabs.py',
    'test_git_ui_actions.py', 'test_git_ui_actions_2.py', 'test_git_ui_files.py',
    'test_git_ui_history.py', 'test_git_ui_history_2.py', 'test_git_ui_lifecycle.py',
    'test_git_ui_operations.py', 'test_git_ui_operations_2.py',
    'test_git_ui_presentation.py', 'test_git_watchers.py',
))


def require_parallel_environment():
    if (sys.platform != 'darwin' or os.environ.get('QT_QPA_PLATFORM') != 'offscreen'
            or os.environ.get('TOGA_BACKEND')):
        raise ValueError('Two test workers currently require macOS and QT_QPA_PLATFORM=offscreen.')
    if os.environ.get('BUILD_MANAGER_TEST_PROGRESS') == '1':
        raise ValueError('Managed phases retain their existing worker admission; use one test worker.')
    try:
        from build_manager.executor import stop_process
    except ImportError as error:
        raise ValueError('Two test workers require the project-pinned build manager process owner.') from error
    if not callable(stop_process):
        raise ValueError('The build manager must provide owned process cleanup.')


def eligible(path):
    try:
        name = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return False
    return name in QT_FILES and not os.environ.get('TOGA_BACKEND')


@contextmanager
def cancellation():
    event = Event()
    previous = {}
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, lambda *_: event.set())
        yield event
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


@contextmanager
def cooperate():
    """Let existing command supervisors retire their own detached helpers."""
    from commonUtils.runtime import operations
    from commonUtils.integrations.wrappers.cmdShellWrapper import capture
    marker = Path(os.environ['LOGISTICS_TEST_CANCEL_FILE'])
    check = operations.check_cancelled
    def check_parent_and_operation(cancelled):
        check(lambda: marker.exists() or cancelled())
    with patch.object(operations, 'check_cancelled', check_parent_and_operation), \
            patch.object(capture, 'check_cancelled', check_parent_and_operation):
        yield


def child(command, environment, timeout, cancelled):
    """Own the entire child process group, including after its leader exits."""
    from build_manager.executor import stop_process
    process = subprocess.Popen(command, env=environment, start_new_session=True)
    deadline = monotonic() + timeout
    try:
        while True:
            remaining = deadline - monotonic()
            if cancelled.is_set() or remaining <= 0:
                outcome = (130, 'cancelled') if cancelled.is_set() else (124, 'timeout')
                # commonUtils capture checks cancellation every 50 ms and its
                # existing supervisor allows up to two 2-second cleanup waits.
                # Fix the deadline outcome before allowing the cleanup grace.
                Path(environment['LOGISTICS_TEST_CANCEL_FILE']).touch()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                return outcome
            try:
                return process.wait(timeout=min(.05, remaining)), None
            except subprocess.TimeoutExpired:
                pass
    finally:
        stop_process(process, grace=.25)


def schedule(plan, execute, report, directory, *, workers, mode, fail_fast, cancelled):
    """Preserve stage and exclusive barriers; aggregate in source-plan order."""
    results = {}
    unstarted = {}
    reason = ''
    failed = False

    def mark(indices, why):
        for index in indices:
            stage, row = plan[index]
            unstarted[index] = dict(file=str(row.path.relative_to(directory)), stage=stage.value,
                cases=[case for case in row.inventory() if case['stage'] == stage.value], reason=why)

    def save():
        if report is None:
            return
        for key in ('tests', 'modules', 'not_run'):
            report.data[key] = [record for index in sorted(results) for record in results[index][1].get(key, [])]
        report.data['not_run'].extend(unstarted[index] for index in sorted(unstarted))
        complete = not unstarted and all(data.get('coverage_complete', False) for _, data in results.values())
        report.data.update(coverage_complete=complete, stopped_early=not complete,
                           cancelled=cancelled.is_set(), workers=workers)
        report.save()

    # Exact stage barriers also prevent two stages of one file overlapping.
    stages = list(dict.fromkeys(stage for stage, _ in plan))
    @contextmanager
    def retire_on_error():
        try:
            yield
        except BaseException:
            cancelled.set()
            for future, (index, _) in active.items():
                try:
                    results[index] = future.result()
                except BaseException:
                    pass
            mark((i for i in range(len(plan)) if i not in results), 'Scheduler interrupted')
            save()
            raise
    active = {}
    with ThreadPoolExecutor(max_workers=workers) as pool, retire_on_error():
        for stage in stages:
            pending = [i for i, item in enumerate(plan) if item[0] is stage]
            active = {}
            stage_failed = False
            while pending or active:
                if cancelled.is_set():
                    reason = 'Cancelled before file started'
                if reason:
                    mark(pending, reason)
                    pending.clear()
                while pending and len(active) < workers:
                    index = pending[0]
                    concurrent = eligible(plan[index][1].path)
                    if active and (not concurrent or any(not allowed for _, allowed in active.values())):
                        break
                    pending.pop(0)
                    active[pool.submit(execute, index, cancelled)] = (index, concurrent)
                    if not concurrent:
                        break
                if not active:
                    break
                done, _ = wait(active, timeout=.05, return_when=FIRST_COMPLETED)
                for future in done:
                    index, _ = active.pop(future)
                    code, data = future.result()
                    results[index] = (code, data)
                    if code:
                        failed = stage_failed = True
                        preflight = any(r['exit_code'] == 2 for r in data.get('modules', []))
                        if fail_fast or mode == 'fast' and preflight:
                            reason = 'Fail-fast failure' if fail_fast else 'Test discovery/preflight failed'
                if done:
                    save()
            if mode == 'fast' and stage.value == 'smoke' and stage_failed:
                reason = 'Smoke gate failed'
        save()
    return 130 if cancelled.is_set() else int(failed)
