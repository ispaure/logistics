"""Project-owned guest evidence collection and conditional cleanup outcomes."""
import json
from pathlib import Path
import subprocess
import time


class GuestResultLifecycle:
    def __init__(self, result, directory, backend, workspace_key):
        self.result, self.directory = result, Path(directory)
        self.backend, self.workspace_key = backend, workspace_key
        self.started = time.monotonic()
        self.collected = False

    def collect(self, collect, evidence, cleanup):
        """Collect before cleanup; preserve remote evidence if transfer fails.

        Collection success and evidence validity are distinct: an invalid report
        is retained locally for diagnosis, allowing the owned remote copy to be
        removed just as before. Transport admission/retry stays with each backend.
        """
        try:
            collect()
            self.collected = True
            evidence = Path(evidence)
            if evidence.is_file():
                report = json.loads(evidence.read_text())
                if report['source'] != self.result['source'] or report['backend'] != self.backend:
                    raise ValueError('Retrieved guest report belongs to different source/backend.')
                self.result['phases'] = report['phases']
                self.result['guest_result'] = str(evidence)
                if self.result['status'] == 'passed' and report['status'] != 'passed':
                    raise ValueError('Guest exit status disagrees with its required test result.')
            elif self.result['status'] == 'passed':
                raise ValueError('A passing guest process did not produce its required result.')
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
            self.result.update(status='failed', retrieval_error=str(error))
        if self.collected:
            try:
                cleanup()
                self.result[self.workspace_key + '_removed'] = True
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                self.result.update(status='failed', cleanup_error=str(error))
        else:
            self.result[self.workspace_key + '_preserved_for_recovery'] = True

    def finish(self):
        self.result['seconds'] = time.monotonic() - self.started
        (self.directory / 'result.json').write_text(json.dumps(self.result, indent=2) + '\n')
        print(json.dumps(self.result), flush=True)
