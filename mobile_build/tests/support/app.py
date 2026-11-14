"""Disposable synchronous host apps; preserve failed cleanup evidence."""
import asyncio
from contextlib import contextmanager, ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import toga
from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.settings import WAIT_TIMEOUT
from mobile.app import LogisticsMobile


def _retire_document_app(app):
    """Release disposable resources even when normal app exit would be vetoed."""
    from mobile.application_lifecycle import lifecycle

    with ExitStack() as cleanup:
        windows = tuple(app.windows)
        for window in windows:
            cleanup.callback(window.close)
        if windows:
            # Dummy Toga's App.exit() only records the request. Clear the main
            # window designation before closing so every window detaches.
            cleanup.callback(setattr, app, 'main_window', None)
        cleanup.callback(lifecycle(app).abort_startup)
        # Retire these directly so disposal errors surface as fixture failures.
        owner = getattr(app, 'vault_browser', None)
        if owner is not None:
            cleanup.callback(owner.dispose)
        panels = dict.fromkeys((*getattr(app, '_notebook_views', {}).values(),
                               getattr(app, 'notebook_panel', None)))
        panels.pop(None, None)
        for panel in panels:
            cleanup.callback(panel.dispose)
        private = getattr(app, 'private_sessions', None)
        if private is not None and not private.terminal:
            # Tests can end with a dirty draft. Test storage is already disposable.
            cleanup.callback(private.retire)
            cleanup.callback(private._admit_retirement)
        manager = getattr(app, 'scene_manager', None)
        if manager is not None:
            cleanup.callback(manager.external_comics.dispose)


def _join_document_index(index):
    worker = index.runner.worker
    if worker.ident is not None:
        worker.join(WAIT_TIMEOUT)
        if worker.is_alive():
            raise AssertionError('Document fixture index worker did not stop')
    if not index.closed:
        raise AssertionError('Document fixture index lease is still open')


@contextmanager
def mobile_app(*, root=None, storage_subdir=None, retire_documents=False):
    """Own constructor-allocated loops and restore the enclosing app/loop.

    Async cases own their running loop and must use a separate lifecycle.
    If cleanup fails, an owned root is retained and named in the exception.
    Caller-supplied roots remain the caller's responsibility on cleanup failure.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError('mobile_app requires a synchronous test case')
    directory = None
    if root is None:
        evidence = Path(__file__).resolve().parents[3] / 'test-results' / 'mobile-fixtures'
        evidence.mkdir(parents=True, exist_ok=True)
        directory = TemporaryDirectory(prefix='app-', dir=evidence, delete=False)
        root = directory.name
    policy = asyncio.get_event_loop_policy()
    allocated = []
    allocate = policy.new_event_loop
    def new_loop():
        loop = allocate()
        allocated.append(loop)
        return loop
    previous = None
    storage = Path(root) if storage_subdir is None else Path(root) / storage_subdir
    with patch.object(LogisticsMobile, 'storage_root', storage), patch.object(toga.App, 'app', toga.App.app):
        try:
            # Tracking before construction covers failures inside Toga startup.
            # A getter-created implicit loop is owned too, not a previous loop.
            with patch.object(policy, 'new_event_loop', side_effect=new_loop):
                try:
                    previous = asyncio.get_event_loop()
                except RuntimeError:
                    previous = None
                if previous in allocated:
                    previous = None
                app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            yield app
        finally:
            try:
                with ExitStack() as cleanup:
                    candidate = toga.App.app
                    owned = candidate is not None and getattr(candidate, 'loop', None) in allocated
                    if owned and retire_documents:
                        index = getattr(candidate, '_directory_index_host', None)
                        if index is not None:
                            cleanup.callback(_join_document_index, index)
                    for loop in allocated:
                        cleanup.callback(close_loop, loop)
                    if owned and retire_documents:
                        cleanup.callback(_retire_document_app, candidate)
                    elif owned:
                        try:
                            window = candidate.main_window
                        except (ValueError, AttributeError):
                            # Toga raises before startup has assigned a window.
                            window = None
                        if window is not None:
                            cleanup.callback(window.close)
                if directory is not None:
                    directory.cleanup()
            except BaseException as error:
                if directory is not None:
                    error.add_note('Retained mobile test fixture after cleanup failure: ' + str(root))
                raise
            finally:
                asyncio.set_event_loop(previous)


def create_app(case, *, root=None):
    """Register app cleanup even if later unittest setUp steps fail."""
    return case.enterContext(mobile_app(root=root))


def create_document_app(case, *, storage_subdir=None):
    """Give a synchronous integration case private Toga history and storage."""
    from toga_dummy.utils import EventLog
    from mobile import palette

    for colors in (palette.LIGHT, palette.DARK):
        case.enterContext(patch.dict(colors))
    case.enterContext(patch('services.appearance_palette._eink_enabled', palette.eink_enabled()))
    case.enterContext(patch.object(palette, '_android_system_dark', palette._android_system_dark))

    case.enterContext(patch.object(EventLog, '_log', []))
    case.enterContext(patch.object(EventLog, '_next_sequence', 0))
    return case.enterContext(mobile_app(storage_subdir=storage_subdir, retire_documents=True))
