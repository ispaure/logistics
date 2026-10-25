"""Owned POSIX native-tool commands shared by the mobile project adapters."""
import subprocess

from build_manager.executor import stop_process

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
        # Retire descendants even when the immediate child has already exited.
        stop_process(process)
