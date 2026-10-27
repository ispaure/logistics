"""Logistics policy for one captured multi-platform validation/delivery journey."""
from dataclasses import dataclass, replace
import json
from pathlib import Path
import re
import sys
from uuid import uuid4

from build_manager import Phase, Plan
from build_manager.credentials import reject_secrets
from build_manager.journeys import request, validate_plan
from build_manager.workflows import EXTERNAL, ancestors


@dataclass(frozen=True)
class PlanningContext:
    root: str
    revision: str
    captured: str

    def source(self, project, revision):
        if str(project.root) != self.root or revision != self.revision:
            raise ValueError('The shared planning context belongs to different source.')
        return json.loads(self.captured)


RUN_FIELDS={'devices.android_signing','devices.android_connections','devices.android_variant','devices.ios_variant','devices.android','devices.ios','testers.message','testflight.what_to_test','firebase.release_notes','testflight.external_group','firebase.group'}


def run_values(values):
    reject_secrets(values)
    if not isinstance(values,dict) or set(values)-RUN_FIELDS or any(not isinstance(v,str) or len(v)>20000 for v in values.values()):
        raise ValueError('Only tester notes and recipient groups can be changed for one run.')
    result = dict(values)
    if result.get('devices.android_signing', 'debug') not in {'debug', 'beta'}:
        raise ValueError('Choose Debug or the existing Beta key for Android device signing.')
    if 'testers.message' in result:
        message = result.pop('testers.message')
        # Saved forms use an empty shared field when the service notes differ.
        # Preserve those explicit notes; a nonempty shared edit still overrides both.
        if message or not any(key in result for key in ('testflight.what_to_test', 'firebase.release_notes')):
            result.update({'testflight.what_to_test': message, 'firebase.release_notes': message})
    from build_manager.run_fields import selection_ids
    if 'devices.android_connections' in result:
        from Scripts.manager_devices import android_connections
        android_connections(result['devices.android_connections'])
    for key in ('devices.android', 'devices.ios'):
        if key in result:selection_ids(result[key])
    for target in ('android', 'ios'):
        if result.get('devices.' + target + '_variant', 'debug') not in {'debug', 'release'}:
            raise ValueError('Choose Debug or Release for device packages.')
    return result


def capture(project, revision, run_overrides=None):
    # Use the canonical project owners, including its real pinned commonUtils.
    from Scripts import build_project as owner
    source = owner.identity(project.root, revision)
    source.update(host=owner.platform.platform(), architecture=owner.platform.machine())
    source['app_version'] = owner.manager_settings.app_version(project.mobile,
        revision=None if revision == 'working-tree' else source['logistics_commit'])
    values, origins = (owner.manager_settings.settings(project.mobile, overrides={key: value for key, value in run_values(run_overrides).items() if not key.startswith('devices.')})
                       if run_overrides else owner.manager_settings.settings(project.mobile))
    if run_overrides:
        source['run_overrides'] = run_values(run_overrides)
    source['effective_settings'] = dict(values=values, origins=origins)
    reject_secrets(source)
    return PlanningContext(str(project.root), revision, json.dumps(source))


def _namespace(plan, prefix, barrier=()):
    """Normalize owned cleanup before combining explicitly shared-context branches."""
    names = {phase.id: prefix + '.' + phase.id for phase in plan.phases}
    phases = []
    for phase in plan.phases:
        dependencies = phase.dependencies
        if phase.always and not dependencies:
            # An unscoped finalizer would wait for unrelated pending deliveries.
            # Exclude consumers of this cleanup (notably release acceptance).
            dependencies = tuple(other.id for other in plan.phases if not other.always
                                 and phase.id not in ancestors(plan, other.id))
        mapped = tuple(names[name] for name in dependencies)
        if not phase.always and not dependencies:
            mapped = (*mapped, *barrier)
        effect = phase.effect if phase.effect != 'inherit' else plan.effect
        phases.append(replace(phase, id=names[phase.id], dependencies=mapped,
                              waits_for=tuple(names[key] for key in phase.waits_for), effect=effect,
                              kind='publication' if effect == 'publish' and phase.kind == 'test' else phase.kind,
                              section='platforms' if prefix.endswith('.validation') else 'delivery'))
    return phases


def make_journey(project, intent, *, revision='working-tree', pattern='', build_override='', release_tag='', backends=None, run_overrides=None):
    if not isinstance(intent, dict):
        raise ValueError('A Logistics journey needs a structured intent.')
    selected = request(project.journey_capability, intent.get('goal'), intent.get('platforms', []), intent.get('destinations', []), backends=backends or intent.get('backends'))
    if intent.get('schema') != 1:
        raise ValueError('Unsupported Logistics journey intent schema.')
    targets, destinations = selected['platforms'], selected['destinations']
    delivery = selected['goal'] == 'deliver'
    overrides = run_values(run_overrides or {})
    release_devices = {target for target in ('android', 'ios') if target + '-devices' in destinations
                       and overrides.get('devices.' + target + '_variant', 'debug') == 'release'}
    if any(name not in {'github', 'firebase', 'testflight', 'android-devices', 'ios-devices'} for name in destinations):
        raise ValueError('This Logistics destination has no reviewed integrated delivery implementation.')
    if pattern:
        raise ValueError('Combined validation uses complete project suites. Use an advanced operation for focused checks.')
    locations = selected.get('backends', {})
    for target in targets:
        row = project.journey_capability['platforms'][target]
        if locations.get(target,row['backend']) not in project.backend_options(target, 'Test'):
            raise ValueError(target + ': the declared validation host is unavailable; no hosted fallback was selected.')
    from Scripts.build_retention import clean
    try:
        clean(project.root, apply=True)
    except (OSError, RuntimeError) as error:
        print('Build retention incomplete: ' + str(error), flush=True)
    context = capture(project, revision, run_overrides)
    source = context.source(project, revision)
    if delivery and source['dirty'] and (any(name in destinations for name in ('github', 'firebase', 'testflight')) or release_devices):
        names = [project.journey_capability['destinations'][name]['label'].split(' · ')[0]
                 for name in destinations if name in {'github', 'firebase', 'testflight'} or name.split('-')[0] in release_devices]
        raise ValueError(', '.join(names) + ' requires committed source. Commit the edits you want to deliver, or choose Latest commit to exclude them.'
                         + (' GitHub releases also require a clean current checkout.' if 'github' in destinations else ''))
    values = source['effective_settings']['values']
    if 'github' in destinations and not release_tag:
        from Scripts.release_naming import suggest_tag, source_version
        release_tag = suggest_tag(project.root, source_version(project.root, source['logistics_commit']))
    for name,target in (('testflight','ios'),('firebase','android')):
        if name in destinations and locations.get(target,project.journey_capability['platforms'][target]['backend']) == 'GitHub':
            raise ValueError(name+' preparation needs local native validation and matching receipts. Choose the local host for '+target+' or remove this delivery destination; GitHub validation is available for checks-only runs.')
    if 'github' in destinations:
        from Scripts.build_snapshots import git
        if git(project.root, 'status', '--porcelain') or git(project.root, 'rev-parse', 'HEAD') != source['logistics_commit']:
            raise ValueError('GitHub publication uses the current clean checkout. Commit intended changes and select its HEAD before planning a release.')
    if any(name in destinations for name in ('firebase', 'testflight')) and sys.platform != 'darwin':
        raise ValueError('Local tester preparation currently requires the configured macOS signing/build host.')

    device_targets = {}
    from Scripts.manager_devices import selected_devices
    for target in ('android', 'ios'):
        if target + '-devices' in destinations:
            if sys.platform != 'darwin':raise ValueError('Device app preparation currently requires the configured Mac build host.')
            if locations.get(target, project.journey_capability['platforms'][target]['backend']) == 'GitHub':
                raise ValueError('Choose local validation for device delivery; hosted evidence is not linked to local development packages.')
            device_targets[target] = selected_devices(project.root, target, run_values(run_overrides or {}))

    phases, gates, locks, resources, capacities = [], {}, set(), {}, {}
    branch_sources, evidence, executions = {}, {}, {}
    plans = []
    def retain(plan):
        plans.append(plan)
        locks.update(plan.resource_locks)
        locks.add(str(Path(plan.workspace) / 'operation.lock'))
        for name, amount in plan.resources.items():
            resources[name] = max(resources.get(name, 0), amount)
        for name, amount in plan.capacities.items():
            if name in capacities and capacities[name] != amount:
                raise ValueError('Project branches disagree about resource capacity: ' + name)
            capacities[name] = amount

    for target in targets:
        row = project.journey_capability['platforms'][target]
        mobile = target in {'ios', 'android'}
        backend = locations.get(target,row['backend'])
        plan = project.make_plan('Test', target, backend, revision=revision,
            include_ipad=delivery and target == 'ios', _context=context,
            _release_validation=delivery and mobile and (('testflight' if target == 'ios' else 'firebase') in destinations or target in release_devices))
        retain(plan)
        branch_sources[target] = plan.source
        branch = _namespace(plan, target + '.validation')
        if any(phase.effect in EXTERNAL - {'dispatch'} for phase in branch):
            raise ValueError('Validation cannot publish or deliver builds.')
        executions[target] = dict(backend=backend,steps=[phase.id for phase in branch if phase.effect=='dispatch'])
        phases.extend(branch)
        gate = Phase(target + '.validated', (str(project.interpreter), '-c', 'pass'), str(project.root),
            dependencies=tuple(phase.id for phase in branch), effect='test', section='platforms')
        phases.append(gate)
        gates[target] = [gate.id]

    preparations = {}
    for target, provider, operation in (('ios', 'testflight', 'Prepare TestFlight'), ('android', 'firebase', 'Prepare Firebase')):
        if provider not in destinations and target not in release_devices:continue
        plan = project.make_plan(operation, target, 'This Mac', revision=revision,
                                 build_override=build_override, _context=context)
        if target == 'ios' and provider not in destinations:
            plan = replace(plan, phases=tuple(p for p in plan.phases if p.id != 'prepare-verified-artifact'))
        retain(plan)
        preparation = _namespace(plan, target + '.preparation', tuple(gates[target]))
        if any(phase.effect in EXTERNAL for phase in preparation):
            raise ValueError('Release preparation must stop before delivery.')
        phases.extend(preparation)
        preparations[target] = preparation

    for name in destinations:
        required_platforms = list(project.journey_capability['destinations'][name]['platforms'])
        required_gates = tuple(step for target in required_platforms for step in gates[target])
        if name in {'android-devices', 'ios-devices'}:
            from Scripts.manager_devices import make_plan as device_plan
            target = required_platforms[0]
            shared = None
            if target in release_devices:
                shared = next((p for p in preparations[target] if p.id.endswith('.build-release-archive')), preparations[target][-1])
            plan = (device_plan(project, target, device_targets[target], context, revision, shared=shared) if shared else
                    device_plan(project, target, device_targets[target], context, revision))
            retain(plan)
            branch = _namespace(plan, target + '.devices', (*required_gates, *((shared.id,) if shared else ())))
            phases.extend(branch)
            evidence[name] = dict(identity='Install in place · ' + ', '.join(row['name'] + ' [' + row['id'] + ']' for row in device_targets[target]),
                steps=[phase.id for phase in branch if phase.effect == 'deploy'], platforms=required_platforms)
            continue
        if name == 'github':
            plan = project.make_plan('Release', targets[0], 'GitHub', revision=revision,
                                     release_tag=release_tag, _context=context)
            retain(plan)
            branch = _namespace(plan, 'github.delivery')
            branch = [replace(phase, dependencies=tuple(dict.fromkeys((*phase.dependencies, *required_gates)))) for phase in branch]
            phases.extend(branch)
            evidence[name] = dict(identity=values['github.repository'] + ' · ' + release_tag +
                ' · commit ' + source['logistics_commit'] + ' · pushes shared/app source and tag; hosted release ZIP (separate from local tester packages)',
                steps=[phase.id for phase in branch if phase.effect in EXTERNAL], platforms=required_platforms)
            continue
        target, operation, provider = ('ios', 'Prepare TestFlight', 'testflight') if name == 'testflight' else ('android', 'Prepare Firebase', 'firebase')
        preparation = preparations[target]
        output = preparation[-1]
        report = Path(output.artifacts[0])
        receipt = report.with_name(report.stem + '-distribution.json')
        upload = Phase(name + '.upload', (output.argv[0], '-m', 'Scripts.distribute_prepared',
            '--report', str(report), '--receipt', str(receipt)), output.cwd, timeout=14400,
            dependencies=(*required_gates, *(phase.id for phase in preparation)), environment=dict(output.environment),
            kind='distribution', effect='upload', provider=provider, artifacts=(str(receipt),),
            label='Upload to ' + ('TestFlight' if name == 'testflight' else 'Firebase'), section='delivery',
            resources={'provider.destination:' + provider + ':Logistics': 1})
        phases.append(upload)
        identity = (str(values['testflight.app_id']) + ' · ' + values['testflight.external_group']
                    if name == 'testflight' else values['firebase.app_id'] + ' · ' + values['firebase.group'])
        evidence[name] = dict(identity=provider + ' · app ' + identity + ' · version ' + source['app_version'], steps=[upload.id], platforms=required_platforms)

    # Refuse changes during preparation, including changing selected settings.
    final = capture(project, revision, run_overrides).source(project, revision)
    if final != source:
        raise ValueError('Source or effective settings changed during combined planning. Prepare a fresh plan.')
    # Preparation-only work is intentionally not an external effect. All deliveries
    # carry explicit effects and retain the existing session/artifact-scoped review.
    workspace = project.private / 'workspaces' / 'journeys' / uuid4().hex
    secrets = tuple(dict.fromkeys(secret for plan in plans for secret in plan.secret_environment))
    result = Plan('Logistics', 'Validate and deliver' if delivery else 'Validate selected platforms',
        dict(source, platform_plans=branch_sources), tuple(phases), str(workspace),
        backend='Per-platform execution choices', max_workers=4, capacities=capacities, resources=resources,
        resource_locks=tuple(sorted(locks)), secret_environment=secrets,
        journey=dict(schema=1, goal=selected['goal'], platforms=gates, destinations=evidence, executions=executions))
    validate_plan(result, selected)
    return result
