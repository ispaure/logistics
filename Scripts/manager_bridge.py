"""Versioned trusted adapter subprocess; never imported by the manager GUI."""
import contextlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'Python')]


def main():
    request = json.load(sys.stdin)
    if request.get('schema') != 1:
        raise ValueError('Unsupported bridge schema.')
    from Scripts.build_project import LogisticsProject
    import os
    os.environ['LOGISTICS_MANAGER_ACCOUNT_DEFAULTS'] = json.dumps(request.get('account_defaults', {}))
    project = LogisticsProject(ROOT)
    values = request.get('values', {})
    action = request['action']
    with contextlib.redirect_stdout(sys.stderr):
        if action == 'plan':
            result = project.make_plan(values.pop('operation'), values.pop('target'), values.pop('backend'), **values).data()
        elif action == 'journey_plan':
            intent = values.pop('intent')
            if intent.get('schema') != 1:
                raise ValueError('Unsupported journey request schema.')
            result = project.make_journey(intent['goal'], intent['platforms'], intent['destinations'], backends=intent.get('backends'), **values).data()
        elif action == 'run_choices':
            from Scripts.manager_devices import choices
            result = choices(ROOT)
        elif action == 'run_defaults':
            result = project.run_defaults()
        elif action == 'settings':
            result = project.settings_view()
        elif action == 'save_settings':
            result = project.save_settings(values['changes'])
        elif action == 'verification':
            result = project.verification_plan().data()
        else:
            raise ValueError('Unsupported bridge action.')
    print(json.dumps(dict(schema=1, result=result)))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        from build_manager.redaction import Redactor
        print(Redactor()(str(error)), file=sys.stderr)
        raise SystemExit(1)
