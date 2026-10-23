"""Run local device deployments and tester distributions sequentially."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
STEPS = (
    ('iOS device install', 'deploy_ios.command'),
    ('Android device install', 'deploy_android.command'),
    ('iOS TestFlight distribution', 'deploy_ios_testflight.command'),
    ('Android Firebase distribution', 'deploy_android_firebase.command'),
)


def deploy_all(*, ask=input):
    failed = []
    for label, launcher in STEPS:
        print('\nStarting ' + label, flush=True)
        result = subprocess.run([str(ROOT / launcher)], cwd=ROOT)
        if result.returncode:
            failed.append(label)
            if ask(label + ' failed. Continue with the remaining deployments? [y/N] ').strip().lower() not in ('y', 'yes'):
                break
    if failed:
        print('Failed: ' + ', '.join(failed), file=sys.stderr)
        return 1
    print('All launchers completed. Distribution prompts determine which builds were uploaded.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(deploy_all())
    except (OSError, EOFError, KeyboardInterrupt) as error:
        print('Deploy all stopped: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
