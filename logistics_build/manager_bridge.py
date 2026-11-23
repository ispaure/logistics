"""Versioned trusted adapter subprocess; never imported by the manager GUI."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import contextlib
from io import StringIO
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'Python')]


def main():
    payload = sys.stdin.read()
    request = json.loads(payload)
    if not isinstance(request, dict) or request.get('schema') != 1:
        raise ValueError('Unsupported bridge schema.')
    # Setup remains available before the external SDK exists in this interpreter.
    if request.get('action') in {'tooling_status', 'tooling_update'}:
        from logistics_build.tooling_bootstrap import handle
        values = request.get('values', {})
        if not isinstance(values, dict):
            raise ValueError('Invalid tooling request.')
        with contextlib.redirect_stdout(sys.stderr):
            result = handle(ROOT, request['action'], values)
        print(json.dumps(dict(schema=1, result=result)))
        return 0
    from build_manager.adapter_sdk import serve

    # Replay the request after the SDK-free bootstrap routing above.
    action = request.get('action')
    if not isinstance(action, str):
        raise ValueError('Unsupported bridge action.')
    serve({action: lambda values, context: dispatch(action, values, context)}, stdin=StringIO(payload))
    return 0


def dispatch(action, values, context):
    from logistics_build.build_project import LogisticsProject
    os.environ['LOGISTICS_MANAGER_ACCOUNT_DEFAULTS'] = json.dumps(context.get('account_defaults', {}))
    if context.get('settings_profile'):
        os.environ.setdefault('LOGISTICS_MANAGER_PROFILE', context['settings_profile'])
        os.environ['LOGISTICS_MANAGER_LEGACY_PROFILE'] = str(ROOT / 'mobile_build/.tools/build-manager/profile.json')
    if context.get('manager_checkout'):
        os.environ['LOGISTICS_MANAGER_CHECKOUT'] = context['manager_checkout']
    project = LogisticsProject(ROOT, results_directory=context.get('results_directory'))
    if action == 'plan':
        result = project.make_plan(values.pop('operation'), values.pop('target'), values.pop('backend'), **values).data()
    elif action == 'journey_plan':
        intent = values.pop('intent')
        if intent.get('schema') != 1:
            raise ValueError('Unsupported journey request schema.')
        result = project.make_journey(intent['goal'], intent['platforms'], intent['destinations'], backends=intent.get('backends'), **values).data()
    elif action == 'retained_delivery_plan':
        result = project.retained_delivery_plan(values['run_directory'], values['destinations'],
                                                 values.get('run_overrides')).data()
    elif action == 'run_choices':
        from logistics_build.manager_devices import choices
        result = choices(ROOT)
    elif action == 'run_defaults':
        result = project.run_defaults()
    elif action == 'settings':
        result = project.settings_view()
    elif action == 'set_app_version':
        result = project.set_app_version(values['version'])
    elif action == 'save_settings':
        result = project.save_settings(values['changes'], resets=values.get('resets', ()))
    elif action == 'verification':
        result = project.verification_plan().data()
    elif action == 'storage_inventory':
        result = project.storage_inventory()
    elif action == 'storage_maintenance':
        from logistics_build.build_retention import storage_maintenance
        result = storage_maintenance(ROOT)
    elif action == 'enroll_storage':
        from logistics_build.storage_extras import enroll
        result = enroll(ROOT, values['kind'], values['location'])
    elif action == 'delete_storage':
        result = project.delete_storage(values['selections'])
    else:
        raise ValueError('Unsupported bridge action.')
    if isinstance(result, dict) and all(key in result for key in ('phases', 'source', 'workspace')):
        from logistics_build.tooling_bootstrap import lock_path
        result['resource_locks'] = list(dict.fromkeys([*result.get('resource_locks', ()), str(lock_path(ROOT))]))
    return result


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ImportError, OSError, ValueError, RuntimeError) as error:
        try:
            from build_manager.redaction import Redactor
        except ImportError:
            print('Project tooling is unavailable; inspect tooling readiness or explicitly update it.', file=sys.stderr)
        else:
            print(Redactor()(str(error)), file=sys.stderr)
        raise SystemExit(1)
