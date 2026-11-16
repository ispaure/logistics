"""Schedule reviewed offscreen test files in isolated processes."""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
import os
from pathlib import Path
import signal
import subprocess
import sys
from threading import Event, Lock, Thread
from time import monotonic
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SUPPORTED_WORKERS = (1, 2, 4, 8)
RESERVATION_ENV = 'BUILD_MANAGER_RESERVED_TEST_WORKERS'
# Explicit files, rather than a directory glob: a newly added test starts
# exclusive until its resources and concurrent behavior have been reviewed.
# The macOS browser files that require real file watchers run alone because
# their filesystem notifications have timed out during pooled execution.
QT_GROUPS = {
    'Python/tests/version_control': (
        'test_git_backend.py',
        'test_git_commands.py',
        'test_git_diff_view.py',
        'test_git_hunk_layout.py',
        'test_git_menu_retirement.py',
        'test_git_merge.py',
        'test_git_models.py',
        'test_git_preferences.py',
        'test_git_repository_tabs.py',
        'test_git_ui_actions.py',
        'test_git_ui_actions_2.py',
        'test_git_ui_files.py',
        'test_git_ui_history.py',
        'test_git_ui_history_2.py',
        'test_git_ui_lifecycle.py',
        'test_git_ui_operations.py',
        'test_git_ui_operations_2.py',
        'test_git_ui_presentation.py',
        'test_git_watchers.py',
    ),
    'Python/tests/editing': (
        'test_code_font.py',
        'test_document_launchers.py',
        'test_editor_changes.py',
        'test_editor_hunks.py',
        'test_editor_resource_picker.py',
        'test_markdown_library_modes.py',
        'test_notes_breadcrumbs.py',
        'test_notes_library_connections.py',
        'test_notes_library_desktop.py',
        'test_notes_library_folders.py',
        'test_notes_library_navigation.py',
        'test_notes_link_cache_policy.py',
        'test_notes_playlists.py',
        'test_obsidian_registry.py',
        'test_text_editor.py',
        'test_text_editor_extensions.py',
        'test_text_editor_recovery.py',
    ),
    'Python/commonUtils/tests/browser': (
        'test_browser_index_policy.py',
        'test_browser_model_metadata.py',
        'test_browser_polish.py',
        'test_browser_presentation.py',
        'test_browser_scan_request.py',
        'test_browser_size_sort.py',
        'test_entry_views.py',
        'test_features.py',
        'test_search.py',
        'test_search_columns.py',
        'test_search_delay.py',
        'test_sqlite_access.py',
        'test_sqlite_browser.py',
        'test_sqlite_browser_integration.py',
    ),
    'Python/commonUtils/tests/index': (
        'test_directory_exclusions.py',
        'test_directory_index.py',
        'test_directory_reconcile.py',
        'test_directory_schema.py',
        'test_directory_search_terms.py',
        'test_discovery_index_ui.py',
        'test_event_driven_index.py',
        'test_index_allocation.py',
        'test_index_coordinator.py',
        'test_index_efficiency.py',
        'test_index_folder_sizes.py',
        'test_index_operation_state.py',
        'test_index_search_jobs.py',
        'test_managed_index_views.py',
        'test_persistent_directory_index.py',
        'test_shared_browser_index.py',
        'test_shared_index_jobs.py',
    ),
    'Python/commonUtils/tests/markdown': (
        'test_markdown.py',
        'test_markdown_frontmatter.py',
        'test_markdown_hover.py',
        'test_markdown_image_sizes.py',
        'test_markdown_image_syntax.py',
        'test_markdown_images.py',
        'test_markdown_links.py',
        'test_markdown_live_edit.py',
        'test_markdown_ownership.py',
        'test_markdown_search.py',
        'test_markdown_speech.py',
        'test_markdown_speech_qt.py',
        'test_markdown_tables.py',
        'test_markdown_wiki.py',
        'test_wiki_catalog.py',
    ),
}
QT_FILES = frozenset(directory + '/' + name for directory, names in QT_GROUPS.items() for name in names)
WINDOWS_GROUPS = {
    'Python/commonUtils/tests/index': (
        'test_directory_exclusions.py', 'test_directory_index.py', 'test_directory_reconcile.py',
        'test_directory_schema.py', 'test_directory_search_terms.py', 'test_discovery_index_ui.py',
        'test_event_driven_index.py', 'test_index_allocation.py', 'test_index_coordinator.py',
        'test_index_efficiency.py', 'test_index_folder_sizes.py', 'test_index_operation_state.py',
        'test_index_search_jobs.py', 'test_integrated_index_search.py', 'test_managed_index_views.py',
        'test_persistent_directory_index.py', 'test_shared_browser_index.py', 'test_shared_index_jobs.py',
    ),
    'Python/commonUtils/tests/browser': (
        'test_browser_file_actions.py', 'test_browser_index_policy.py', 'test_browser_model_metadata.py',
        'test_browser_polish.py', 'test_browser_presentation.py', 'test_browser_scan_request.py',
        'test_browser_size_sort.py', 'test_file_browser.py', 'test_search.py', 'test_search_columns.py',
        'test_search_delay.py', 'test_sqlite_browser.py', 'test_sqlite_browser_integration.py',
    ),
    'Python/tests/version_control': (
        'test_git_backend.py', 'test_git_commands.py', 'test_git_diff_view.py', 'test_git_hunk_layout.py',
        'test_git_menu_retirement.py', 'test_git_merge.py', 'test_git_models.py', 'test_git_preferences.py',
        'test_git_repository_tabs.py', 'test_git_ui_actions.py', 'test_git_ui_actions_2.py',
        'test_git_ui_files.py', 'test_git_ui_history.py', 'test_git_ui_history_2.py',
        'test_git_ui_lifecycle.py', 'test_git_ui_operations.py', 'test_git_ui_operations_2.py',
        'test_git_ui_presentation.py', 'test_git_watchers.py',
    ),
    'Python/tests/editing': (
        'test_code_font.py', 'test_editor_changes.py', 'test_editor_hunks.py', 'test_editor_resource_picker.py',
        'test_notes_library_folders.py', 'test_notes_playlists.py',
        'test_text_editor.py', 'test_text_editor_extensions.py', 'test_text_editor_recovery.py',
    ),
}
WINDOWS_FILES = frozenset(directory + '/' + name for directory, names in WINDOWS_GROUPS.items() for name in names)
# This set passed matched serial and concurrent pilots on Windows and Fedora.
PORTABLE_GROUPS = {
    'Python/commonUtils/tests/runtime': (
        'test_batch.py', 'test_browsing.py', 'test_choices.py', 'test_file_locking.py',
        'test_line_redaction.py', 'test_migrations.py', 'test_persistence.py',
        'test_private_publication.py', 'test_protected_keys.py', 'test_session_store.py',
        'test_sse_framing.py', 'test_streams.py', 'test_transfer_phases.py',
    ),
}
PORTABLE_FILES = frozenset(directory + '/' + name for directory, names in PORTABLE_GROUPS.items() for name in names)
MOBILE_GROUPS = {
    'mobile_build/tests/documents': ('test_editor_picker.py', 'test_notebook_storage.py'),
    'mobile_build/tests/editing': ('test_notes_library_panels.py',),
    'mobile_build/tests/native': ('test_android_back.py',),
    'mobile_build/tests/storage': ('test_storage_reader_opening.py',),
    'mobile_build/tests/workspace': ('test_hub_documents.py', 'test_workspace_navigation.py'),
}
MOBILE_FILES = frozenset(directory + '/' + name for directory, names in MOBILE_GROUPS.items() for name in names)


def require_parallel_environment(workers=2):
    toga = os.environ.get('TOGA_BACKEND')
    if toga:
        supported = sys.platform == 'darwin' and toga == 'toga_dummy'
    else:
        supported = sys.platform in ('darwin', 'linux', 'win32') and os.environ.get('QT_QPA_PLATFORM') == 'offscreen'
    if not supported:
        raise ValueError('Parallel test workers require offscreen Qt on Windows, Linux or macOS, or dummy Toga on macOS.')
    if os.environ.get('BUILD_MANAGER_TEST_PROGRESS') == '1':
        reserved = os.environ.get(RESERVATION_ENV, '')
        if not reserved.isdecimal() or not workers <= int(reserved) <= 8:
            raise ValueError('Managed test workers require a sufficient Manager host/platform reservation.')
    try:
        from build_manager.executor import stop_process
    except ImportError as error:
        raise ValueError('Parallel test workers require the project-pinned build manager process owner.') from error
    if not callable(stop_process):
        raise ValueError('The build manager must provide owned process cleanup.')


def eligible(path):
    try:
        name = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return False
    toga = os.environ.get('TOGA_BACKEND')
    if toga:
        return sys.platform == 'darwin' and toga == 'toga_dummy' and name in MOBILE_FILES
    if sys.platform == 'win32':
        return name in PORTABLE_FILES or name in WINDOWS_FILES
    return name in PORTABLE_FILES or sys.platform == 'darwin' and name in QT_FILES


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


_windows_output_lock = Lock()


@contextmanager
def _windows_child(command, environment):
    """Assign before resume and drain the job's output while the file runs."""
    from build_manager.windows_process import WindowsProcess

    process = WindowsProcess(command, cwd=Path.cwd(), env=environment)
    errors = []

    def forward_output():
        try:
            with process.stdout as stream:
                while line := stream.readline(16384):
                    with _windows_output_lock:
                        sys.stdout.buffer.write(line)
                        sys.stdout.buffer.flush()
        except (OSError, ValueError) as error:
            errors.append(error)

    reader = Thread(target=forward_output, daemon=True)
    try:
        reader.start()
        yield process
    finally:
        try:
            process.kill_tree()
            process.wait_tree()
        finally:
            process.close()
            if reader.ident is None:
                process.stdout.close()
            else:
                reader.join(timeout=5)
                if reader.is_alive():
                    raise RuntimeError('Owned Windows test output did not close.')
        if errors:
            raise RuntimeError('Could not stream Windows test output.') from errors[0]


@contextmanager
def _posix_child(command, environment):
    from build_manager.executor import stop_process

    process = subprocess.Popen(command, env=environment, start_new_session=True)
    try:
        yield process
    finally:
        stop_process(process, grace=.25)


def child(command, environment, timeout, cancelled):
    """Own the entire child process tree, including after its leader exits."""
    launch = _windows_child if os.name == 'nt' else _posix_child
    with launch(command, environment) as process:
        deadline = monotonic() + timeout
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


def schedule(plan, execute, report, directory, *, workers, mode, fail_fast, cancelled,
             group_eligible=False):
    """Preserve stage and exclusive barriers; aggregate in source-plan order."""
    results = {}
    unstarted = {}
    reason = ''
    failed = False

    def mark(indices, why):
        for index in indices:
            stage, row = plan[index]
            unstarted[index] = dict(file=row.path.relative_to(directory).as_posix(), stage=stage.value,
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
            if group_eligible:
                # Coalesce reviewed work to avoid draining the pool between
                # small batches. Stable sorting retains both groups' order.
                pending.sort(key=lambda i: not eligible(plan[i][1].path))
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
