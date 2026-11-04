"""Fresh device delivery from independently verified retained platform evidence.

Original plans/results and captured source are read-only. Fresh recipients,
execution choices, runner copies and receipts belong to a new device workspace.
"""
import argparse
import ast
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

from build_manager import Phase, Plan
from build_manager.credentials import reject_secrets
from build_manager.history import load_run
from build_manager.registry import Registry
from build_manager.run_fields import selection_ids
from build_manager.workflows import transitive_dependency_ids, verify_artifacts
from commonUtils.runtime.streams import file_sha256

DESTINATIONS = {'ios-devices': 'ios', 'android-devices': 'android'}
CHOICES = {'devices.ios', 'devices.android', 'devices.android_connections',
           'devices.ios_provisioning', 'devices.availability'}
SOURCE_KEYS = ('logistics_commit', 'commonUtils_commit', 'dirty', 'commonUtils_dirty', 'fingerprint')
REBUILD = 'Retained build is unavailable or changed. Rebuild and validate the selected platform, then review a new device delivery.'


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _read(path):
    path = Path(path)
    _require(path.is_file() and path.stat().st_size <= 32 * 1024 * 1024, REBUILD)
    return json.loads(path.read_text())


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def verify_snapshot(snapshot, source):
    """Validate an existing capture, including dirty Current Files, without recreating it."""
    from logistics_build.build_snapshots import identity
    snapshot = Path(snapshot).resolve()
    metadata = _read(snapshot / '.manager-source.json')
    _require(all(metadata.get('source', {}).get(key) == source.get(key) for key in SOURCE_KEYS), REBUILD)
    _require(metadata.get('snapshot_fingerprint') == identity(snapshot)['fingerprint'], REBUILD)
    return dict(path=str(snapshot), metadata_sha256=file_sha256(snapshot / '.manager-source.json'),
                snapshot_fingerprint=metadata['snapshot_fingerprint'])


def _trusted(project, plan, snapshot):
    registry = Registry()
    row, descriptor = registry.resolve(registry.project_key(str(project.root)), trusted=True)
    adapter = plan.adapter
    _require(row.get('trusted') is True and Path(row['root']).resolve() == Path(project.root).resolve()
             and Path(adapter.get('checkout', '')).resolve() == Path(project.root).resolve()
             and plan.project == descriptor['name']
             and row['project_id'] == descriptor['project_id'] == adapter.get('project_id')
             and adapter.get('api') == 1, 'Retained run belongs to another trusted project checkout.')
    original_descriptor = snapshot / 'build-project.json'
    _require(original_descriptor.is_file(), REBUILD)
    _require(file_sha256(original_descriptor) == adapter.get('descriptor_sha256'),
             'Original captured adapter descriptor changed. ' + REBUILD)
    return dict(checkout=str(Path(project.root).resolve()), project_id=row['project_id'],
                current_descriptor_sha256=row['descriptor'])


def _source_matches(actual, source):
    return (all(actual.get(key) == source.get(key) for key in ('logistics_commit', 'commonUtils_commit', 'dirty'))
            and actual.get('manager_source_fingerprint') == source['fingerprint'])


def _shared_input(plan, report, platform):
    suffix = '.build-release-archive' if platform == 'ios' else '.prepare-verified-artifact'
    candidates = [phase for phase in plan.phases if phase.id.startswith(platform + '.') and phase.id.endswith(suffix)]
    _require(len(candidates) == 1 and len(candidates[0].artifacts) == 1, 'No applicable retained Release artifact. ' + REBUILD)
    shared = candidates[0]
    needed = transitive_dependency_ids(plan, shared.id) | {shared.id}
    gate = platform + '.validated'
    _require(gate in needed, 'Retained delivery requires the selected platform validation gate. ' + REBUILD)
    needed.update(phase.id for phase in plan.phases if phase.required and phase.always
                  and phase.id.startswith(platform + '.validation.'))
    rows = {row['id']: row for row in report['phases']}
    _require(all(rows.get(key, {}).get('status') == 'passed' for key in needed),
             'Selected platform validation, cleanup or preparation did not pass. ' + REBUILD)
    for key in sorted(needed):
        try:
            verify_artifacts(rows[key])
        except (OSError, ValueError) as error:
            raise ValueError(str(error) + ' ' + REBUILD) from error
    matches = [artifact for artifact in rows[shared.id].get('artifacts', [])
               if Path(artifact.get('original_path', artifact['path'])).resolve() == Path(shared.artifacts[0]).resolve()]
    _require(len(matches) == 1, 'Retained artifact lacks exact copied/original evidence. ' + REBUILD)
    artifact = matches[0]
    path = Path(artifact['path'])
    source = plan.source
    if platform == 'ios':
        from logistics_build.manager_packages import checked_archive
        try:
            state, record = checked_archive(path)
        except (OSError, ValueError, KeyError) as error:
            raise ValueError('Retained iOS archive cannot be verified. ' + REBUILD) from error
        _require(_source_matches(record['source'], source), 'Shared iOS archive source differs. ' + REBUILD)
        details = dict(build_number=state['build_number'], archive_sha256=state['archive_sha256'],
                       release_sha256=state['release_sha256'])
    else:
        record = _read(path)
        _require(record.get('provider') == 'Firebase' and _source_matches(record.get('source', {}), source)
                 and record.get('bundle_id') == 'io.github.ispaure.logisticsmobile'
                 and Path(record.get('apk', '')).is_file()
                 and file_sha256(record['apk']) == record.get('apk_sha256')
                 and re.fullmatch('[0-9a-f]{64}', record.get('certificate', '')),
                 'Shared Android APK source, bytes or certificate differs. ' + REBUILD)
        details = dict(apk_sha256=record['apk_sha256'], certificate=record['certificate'])
    return dict(phase=replace(shared, artifacts=(str(path),)), evidence=artifact, details=details,
                gates={key: rows[key] for key in sorted(needed)})


def inspect_run(project, run_directory, destinations):
    """Verify applicable platform closures; another platform's failure is independent."""
    _require(isinstance(destinations, list) and destinations and all(isinstance(key, str) for key in destinations)
             and len(set(destinations)) == len(destinations)
             and set(destinations) <= set(DESTINATIONS), 'Choose distinct iOS/Android saved-device destinations.')
    output = Path(run_directory).resolve()
    plan, report = load_run(output / 'result.json')
    _require(report['status'] in {'passed', 'failed', 'cancelled', 'awaiting_review'},
             'Wait for the retained controller to stop before preparing separate device delivery.')
    _require(report.get('source') == plan.source and report.get('project') == plan.project,
             'Original retained source/project does not match its plan. ' + REBUILD)
    _require(re.fullmatch('[0-9a-f]{64}', plan.source.get('fingerprint', '')), REBUILD)
    snapshot = Path(project.private) / 'snapshots' / plan.source['fingerprint']
    snapshot_proof = verify_snapshot(snapshot, plan.source)
    trusted = _trusted(project, plan, snapshot)
    shared = {DESTINATIONS[key]: _shared_input(plan, report, DESTINATIONS[key]) for key in destinations}
    binding = dict(original_plan=plan.identity, original_plan_sha256=file_sha256(output / 'plan.json'),
                   original_result_sha256=file_sha256(output / 'result.json'), snapshot=snapshot_proof,
                   trusted=trusted, platforms={key: dict(evidence=value['evidence'], details=value['details'],
                   gates=value['gates']) for key, value in shared.items()})
    return plan, shared, binding


def _choices(project, destinations, overrides, shared):
    from logistics_build.manager_devices import android_connections, android_signing_policy, saved_devices
    _require(overrides is None or isinstance(overrides, dict), 'Retained execution choices must be an object.')
    values = dict(overrides or {})
    reject_secrets(values)
    _require(set(values) <= CHOICES and all(isinstance(value, str) for value in values.values()),
             'Retained delivery permits only recipient, transport, availability and provisioning choices.')
    values.setdefault('devices.availability', 'bounded')
    values.setdefault('devices.ios_provisioning', 'existing')
    _require(values['devices.availability'] in {'bounded', 'wait'}, 'Choose Try once or Wait until reachable.')
    _require(values['devices.ios_provisioning'] in {'existing', 'update'}, 'Choose existing assets or explicit provisioning updates.')
    targets = {}
    for destination in destinations:
        platform = DESTINATIONS[destination]
        ids = selection_ids(values.get('devices.' + platform, '[]'))
        known = saved_devices(project.root, platform)[platform]
        _require(ids and len(ids) == len(set(ids)) and all(key in known for key in ids),
                 'Choose explicit saved ' + platform + ' recipients for this new delivery.')
        targets[platform] = [dict(known[key]) for key in ids]
        if platform == 'android':
            connections = android_connections(values.get('devices.android_connections', '{}'))
            _require(set(connections) <= set(ids), 'Transport choices must name selected saved recipients.')
            for target in targets[platform]:
                policy = android_signing_policy(target.get('android_signing'))
                _require(policy['mode'] == 'beta' and policy['certificate'] == shared[platform]['details']['certificate'],
                         'Saved Android signing policy differs from the retained Firebase APK; build a compatible app explicitly.')
                if target['id'] in connections:
                    target['fallback_connections'] = [target['connection']]
                    target['connection'] = connections[target['id']]
    return values, targets


def _namespace(phases, prefix):
    names = {phase.id: prefix + '.' + phase.id for phase in phases}
    return [replace(phase, id=names[phase.id], dependencies=tuple(names[key] for key in phase.dependencies),
                    waits_for=tuple(names[key] for key in phase.waits_for)) for phase in phases]


def execution_settings(mobile):
    """Resolve current tool paths/API references without VM or device discovery."""
    from build_manager.settings import Field, resolve
    from mobile_build.deployment import manager_settings as owner
    configured = {key: value for key, value in owner.defaults(mobile).items() if key.startswith(('tools.', 'auth.'))}
    profile = {key: value for key, value in owner.current_settings(owner.loaded_profile(mobile)).items() if key in configured}
    account = {key: value for key, value in json.loads(os.environ.get('LOGISTICS_MANAGER_ACCOUNT_DEFAULTS', '{}')).items()
               if key in configured and key.startswith('auth.')}
    schema = {key: Field(value, account=key.startswith('auth.'), machine=key.startswith('tools.'),
                        variable=owner.VARIABLES.get(key)) for key, value in configured.items()}
    return resolve(schema, account=account, profile=profile, environment=os.environ)[0]


def make_plan(project, run_directory, destinations, run_overrides=None):
    from logistics_build import manager_devices as devices
    from logistics_build.manager_journeys import PlanningContext
    from mobile_build.deployment.manager_settings import profile_path
    original, shared, binding = inspect_run(project, run_directory, destinations)
    choices, targets = _choices(project, destinations, run_overrides, shared)
    current = execution_settings(project.mobile)
    execution = dict(current)
    if 'ios' in targets:
        helper = Path(binding['snapshot']['path']) / 'mobile_build/deployment/device_tools.py'
        try:
            functions = {node.name: node for node in ast.parse(helper.read_text()).body if isinstance(node, ast.FunctionDef)} if helper.is_file() else {}
        except (OSError, SyntaxError) as error:
            raise ValueError('Captured iOS validation helper is unavailable. ' + REBUILD) from error
        validator = functions.get('validate_app')
        _require(validator is not None and (validator.args.kwarg is not None or any(
            argument.arg == 'build_number' for argument in (*validator.args.args, *validator.args.kwonlyargs))),
            'Captured iOS helper cannot validate the archive build number. ' + REBUILD)
        if choices['devices.ios_provisioning'] == 'update':
            _require('provisioning_auth_args' in functions, 'Captured source cannot resolve protected provisioning references. Choose existing signing assets or rebuild with the current helper.')
    reject_secrets(execution)
    # Reuse the first owning device recipe workspace, already classified by
    # existing per-platform retention. Do not create a parallel cache hierarchy.
    workspace = runner = verifier = None
    context = PlanningContext(str(project.root), original.source['logistics_commit'], json.dumps(original.source))
    phases = []; locks = list(original.resource_locks); commands = {}; recipes = {}
    for platform, recipients in targets.items():
        owned = devices.make_plan(project, platform, recipients, context, context.revision,
                                  shared=shared[platform]['phase'], retained_snapshot=binding['snapshot']['path'])
        if workspace is None:
            workspace = Path(owned.workspace)
            runner = workspace / 'manager_devices.py'; runner.write_bytes(Path(devices.__file__).read_bytes())
            verifier = workspace / 'retained_devices.py'; verifier.write_bytes(Path(__file__).read_bytes())
        locks.append(str(Path(owned.workspace) / 'operation.lock'))
        _require(all(phase.description != 'Development variant · separate from Release' for phase in owned.phases),
                 'Retained delivery must never fall back to compilation.')
        recipe = Path(owned.workspace) / 'recipe.json'
        data = _read(recipe); data['execution_choices'] = choices
        data['retained_delivery'] = dict(original_run=str(Path(run_directory).resolve()),
                                         original_plan_identity=original.identity, review_digest=_digest(binding))
        _require(data.get('shared_report') == shared[platform]['phase'].artifacts[0], 'Owning plan lost shared artifact.')
        recipe.write_text(json.dumps(data, indent=2) + '\n')
        recipes[str(recipe)] = file_sha256(recipe)
        updated = []
        for phase in _namespace(owned.phases, platform):
            argv = list(phase.argv)
            _require(argv[1:3] == ['-m', 'logistics_build.manager_devices'], 'Unexpected owning device runner.')
            argv[:3] = [current['tools.mobile_python'], str(runner)]
            if '--recipe' in argv:
                argv[argv.index('--sha256') + 1] = recipes[str(recipe)]
            environment = dict(phase.environment)
            environment.update(PYTHONPATH=os.pathsep.join((binding['snapshot']['path'], str(Path(binding['snapshot']['path']) / 'Python'))))
            for key, name in [('tools.xcode', 'DEVELOPER_DIR'), ('tools.android_sdk', 'ANDROID_HOME'), ('tools.java', 'JAVA_HOME')]:
                if execution.get(key): environment[name] = execution[key]
            for name in ('LOGISTICS_MANAGER_PROFILE', 'LOGISTICS_MANAGER_LEGACY_PROFILE', 'LOGISTICS_MANAGER_ACCOUNT_DEFAULTS'):
                if os.environ.get(name):environment[name] = os.environ[name]
            if platform == 'ios' and phase.id.endswith('.prepare-device-app') and choices['devices.ios_provisioning'] == 'update':
                phase = replace(phase, description='Export the verified Release archive; explicitly allow Apple profile/capability updates; no compilation or device registration.')
            if phase.kind == 'connection':
                phase = replace(phase, **devices.availability_policy(choices['devices.availability']))
            if phase.effect == 'deploy':
                phase = replace(phase, approval_required=True)
            updated.append(replace(phase, argv=tuple(argv), environment=environment))
        phases.extend(updated); locks.extend(owned.resource_locks)
    proof = dict(schema=1, root=str(Path(project.root).resolve()), run_directory=str(Path(run_directory).resolve()),
                 destinations=destinations, original_binding=binding, source=original.source,
                 execution_choices=choices, execution_settings=execution, recipients=targets,
                 runner=str(runner), runner_sha256=file_sha256(runner), verifier=str(verifier),
                 verifier_sha256=file_sha256(verifier), recipes=recipes, plan_workspace=str(workspace),
                 execution_profile=dict(path=str(profile_path(project.mobile)),
                     sha256=file_sha256(profile_path(project.mobile)) if profile_path(project.mobile).is_file() else None))
    for phase in phases:
        commands[phase.id] = dict(argv=list(phase.argv), cwd=phase.cwd)
    proof['commands'] = commands
    reject_secrets(proof)
    path = workspace / 'review-inputs.json'; path.write_text(json.dumps(proof, indent=2) + '\n')
    digest = file_sha256(path)
    inputs = tuple(dict.fromkeys([str(path), str(Path(run_directory).resolve() / 'plan.json'),
        str(Path(run_directory).resolve() / 'result.json'),
        *(value['evidence']['path'] for value in shared.values()),
        *(value['evidence'].get('original_path', value['evidence']['path']) for value in shared.values())]))
    gate = Phase('verify-retained-inputs', (current['tools.mobile_python'], str(verifier), 'verify',
        '--proof', str(path), '--sha256', digest), str(workspace), effect='inspect', kind='verification',
        environment=dict(phases[0].environment),
        artifacts=inputs, label='Verify original platform evidence and retained source',
        description='Original failures remain unchanged; verifies only the requested platform closures.')
    wrapped = [gate, *[replace(phase,
        dependencies=phase.dependencies or (gate.id,),
        argv=(current['tools.mobile_python'], str(verifier), 'execute', '--proof', str(path),
              '--sha256', digest, '--step', phase.id, '--', *phase.argv)) for phase in phases]]
    provenance = dict(original_run=str(Path(run_directory).resolve()), original_plan_identity=original.identity,
                      original_review_digest=_digest(binding), proof=str(path), proof_sha256=digest,
                      recipients=targets, execution_choices=choices, execution_settings=execution,
                      source_scope='Original verified snapshot; original failures and source remain unchanged.')
    return Plan(original.project, 'Deliver retained verified mobile artifacts', deepcopy(original.source), tuple(wrapped),
                str(workspace), backend='This Mac', effect='deploy', secret_environment=original.secret_environment,
                resource_locks=tuple(dict.fromkeys(locks)), capacities=original.capacities,
                settings=dict(original.settings, retained_delivery=provenance), adapter=original.adapter,
                max_workers=original.max_workers, resources=original.resources)


def _checked_command(proof, step, argv):
    expected = proof['commands'].get(step)
    _require(expected is not None and len(argv) == len(expected['argv']), 'Retained device command changed.')
    expected_argv = expected['argv']
    for index, (actual, saved) in enumerate(zip(argv, expected_argv)):
        if actual == saved:
            continue
        _require(index > 0 and expected_argv[index - 1] == '--receipt', 'Retained device input command changed.')
        # Generic explicit retry changes outputs only. Device/report/source and
        # recipe still match the original fresh review, never a new recipient.
        output = Path(actual).resolve()
        parent = Path(proof['plan_workspace']).resolve()
        _require(output.is_relative_to(parent), 'Invalid fresh device retry receipt.')
        parts = output.relative_to(parent).parts
        _require(len(parts) >= 3 and len(parts) % 2 == 1
                 and all(parts[index] == 'explicit-device-retries'
                         and re.fullmatch('[0-9a-f]{32}', parts[index + 1])
                         for index in range(0, len(parts) - 1, 2))
                 and re.fullmatch(r'receipt-\d+\.json', parts[-1]), 'Invalid fresh device retry receipt.')
    return expected['cwd']


def verify_inputs(proof_path, digest):
    _require(file_sha256(proof_path) == digest, 'Retained delivery review inputs changed.')
    proof = _read(proof_path)
    _require(file_sha256(Path(__file__)) == proof['verifier_sha256']
             and file_sha256(proof['runner']) == proof['runner_sha256'], 'Reviewed device runner changed.')
    project = SimpleNamespace(root=Path(proof['root']), mobile=Path(proof['root']) / 'mobile_build',
                              private=Path(proof['root']) / 'mobile_build/.tools/build-manager')
    _, _, binding = inspect_run(project, proof['run_directory'], proof['destinations'])
    _require(binding == proof['original_binding'], 'Original retained inputs changed; review a fresh delivery.')
    profile = Path(proof['execution_profile']['path'])
    profile_digest = file_sha256(profile) if profile.is_file() else None
    _require(profile_digest == proof['execution_profile']['sha256'], 'Reviewed execution profile references changed; prepare a fresh delivery.')
    for path, expected in proof['recipes'].items():
        _require(file_sha256(path) == expected, 'Reviewed recipient/signing recipe changed.')
        recipe = _read(path)
        if recipe['platform'] == 'ios':
            _require(file_sha256(recipe['config']) == recipe['config_sha256'],
                     'Reviewed Apple team/recipient configuration changed; prepare a fresh delivery.')
    return proof


def execute(proof_path, digest, step, argv):
    proof = verify_inputs(proof_path, digest)
    cwd = _checked_command(proof, step, argv)
    # Preserve owning exit75 so explicit Wait mode can retry inspection only.
    # No deployment exit is retried by this wrapper.
    return subprocess.run(argv, cwd=cwd, check=False).returncode


def main(arguments=None):
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    separator = arguments.index('--') if '--' in arguments else len(arguments)
    header, command = arguments[:separator], arguments[separator + 1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['verify', 'execute'])
    parser.add_argument('--proof', type=Path, required=True); parser.add_argument('--sha256', required=True)
    parser.add_argument('--step')
    args = parser.parse_args(header)
    if args.action == 'verify':
        _require(not command and args.step is None, 'Verification does not execute a device command.')
        verify_inputs(args.proof, args.sha256)
        return 0
    else:
        _require(args.step and command, 'Execution requires a reviewed device step and command.')
        return execute(args.proof, args.sha256, args.step, command)


if __name__ == '__main__':
    raise SystemExit(main())
