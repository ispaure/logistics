"""App cache identity changes when executable permissions or payload change."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from Scripts.ios_backend import bundle_digest


class BundleIdentityTests(unittest.TestCase):
    def test_payload_and_mode_changes_invalidate_the_bundle(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);binary=root/'binary';binary.write_bytes(b'synthetic');binary.chmod(0o644)
            before=bundle_digest(root);mode=binary.stat().st_mode;binary.chmod(0o755)
            if binary.stat().st_mode!=mode:
                self.assertNotEqual(bundle_digest(root),before)
            else:
                self.assertEqual(bundle_digest(root),before)
            before=bundle_digest(root);binary.write_bytes(b'changed')
            self.assertNotEqual(bundle_digest(root),before)

    @unittest.skipIf(__import__('os').name=='nt','POSIX mobile build helper; Windows executor has Job Object contracts')
    def test_cancelled_mobile_command_retires_a_term_ignoring_child(self):
        import os
        import signal
        import subprocess
        import sys
        import time
        with TemporaryDirectory() as directory:
            root=Path(directory);pid=root/'child.pid'
            child='import os,signal,time;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);Path('+repr(str(pid))+').write_text(str(os.getpid()));time.sleep(90)'
            code='import signal,sys;from Scripts.ios_backend import command,interrupt;signal.signal(signal.SIGTERM,interrupt);command([sys.executable,"-c",'+repr(child)+'],'+repr(str(root))+',30)'
            parent=subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            child_pid=None
            try:
                deadline=time.monotonic()+5
                while not pid.exists():
                    if parent.poll() is not None or time.monotonic()>deadline:self.fail('Synthetic build child did not start')
                    time.sleep(.01)
                child_pid=int(pid.read_text());parent.send_signal(signal.SIGTERM)
                parent.communicate(timeout=4)
                self.assertNotEqual(parent.returncode,0)
                with self.assertRaises(ProcessLookupError):os.kill(child_pid,0)
            finally:
                if parent.poll() is None:parent.kill();parent.communicate(timeout=3)
                if child_pid:
                    try:os.kill(child_pid,signal.SIGKILL)
                    except ProcessLookupError:pass
