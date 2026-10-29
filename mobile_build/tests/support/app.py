"""Disposable synchronous host apps; preserve failed cleanup evidence."""
import asyncio
from contextlib import contextmanager, ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import toga
from commonUtils.testing.event_loop import close_loop
from mobile.app import LogisticsMobile


@contextmanager
def mobile_app(*, root=None):
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
    with patch.object(LogisticsMobile, 'storage_root', Path(root)), patch.object(toga.App, 'app', toga.App.app):
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
                try:
                    app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
                except BaseException:
                    app = toga.App.app
                    raise
            yield app
        finally:
            try:
                with ExitStack() as cleanup:
                    for loop in allocated:
                        cleanup.callback(close_loop, loop)
                    candidate = toga.App.app
                    if candidate is not None and getattr(candidate, 'loop', None) in allocated:
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
