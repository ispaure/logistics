"""Owned POSIX native-tool commands shared by the mobile project adapters."""
import signal
import subprocess

from build_manager.executor import signal_group

def interrupt(*_):
    raise KeyboardInterrupt


def command(argv, cwd, timeout=1200):
    process = subprocess.Popen(argv, cwd=cwd, start_new_session=True)
    try:
        code = process.wait(timeout=timeout)
        if code:
            raise RuntimeError('Native preparation command failed: ' + str(code))
    finally:
        # A cancelled build must not leave Xcode/Briefcase descendants alive.
        try:
            signal_group(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        # The immediate child may already have exited while a descendant holds
        # the group. Retire the owned group even in that case.
        try:
            signal_group(process.pid,signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
