"""Run local device deployments and tester distributions sequentially."""
from pathlib import Path
import subprocess
import sys

from build_manager.deployment_commands import Command, CommandStep, run_sequence

ROOT = Path(__file__).resolve().parents[1]
STEPS = (
    ('iOS device install', 'deploy_ios.command'),
    ('Android device install', 'deploy_android.command'),
    ('iOS TestFlight distribution', 'deploy_ios_testflight.command'),
    ('Android Firebase distribution', 'deploy_android_firebase.command'),
)


def deploy_all(*, ask=input):
    steps = (CommandStep(label, Command((str(ROOT / launcher),), str(ROOT))) for label, launcher in STEPS)
    failed = run_sequence(steps,
        starting=lambda step: print('\nStarting ' + step.label, flush=True),
        continue_after_failure=lambda step, code: ask(step.label +
            ' failed. Continue with the remaining deployments? [y/N] ').strip().lower() in ('y', 'yes'))
    if failed:
        print('Failed: ' + ', '.join(step.label for step in failed), file=sys.stderr)
        return 1
    print('All launchers completed. Distribution prompts determine which builds were uploaded.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(deploy_all())
    except (OSError, EOFError, KeyboardInterrupt) as error:
        print('Deploy all stopped: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
