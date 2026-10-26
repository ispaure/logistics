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


def capture(project, revision):
    # Use the canonical project owners, including its real pinned commonUtils.
    from Scripts import build_project as owner
    source = owner.identity(project.root, revision)
    source.update(host=owner.platform.platform(), architecture=owner.platform.machine())
    source['app_version'] = owner.manager_settings.app_version(project.mobile,
        revision=None if revision == 'working-tree' else source['logistics_commit'])
    values, origins = owner.manager_settings.settings(project.mobile)
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
        phases.append(replace(phase, id=names[phase.id], dependencies=mapped, effect=effect,
                              kind='publication' if effect == 'publish' and phase.kind == 'test' else phase.kind))
    return phases


def make_journey(project, intent, *, revision='working-tree', pattern='', build_override='', release_tag=''):
    if not isinstance(intent, dict):
        raise ValueError('A Logistics journey needs a structured intent.')
    selected = request(project.journey_capability, intent.get('goal'), intent.get('platforms', []), intent.get('destinations', []))
    if intent.get('schema') != 1:
        raise ValueError('Unsupported Logistics journey intent schema.')
    targets, destinations = selected['platforms'], selected['destinations']
    delivery = selected['goal'] == 'deliver'
    if any(name not in {'github', 'firebase', 'testflight'} for name in destinations):
        raise ValueError('This Logistics destination has no reviewed integrated delivery implementation.')
    if pattern:
        raise ValueError('Combined validation uses complete project suites. Use an advanced operation for focused checks.')
    for target in targets:
        row = project.journey_capability['platforms'][target]
        if row['backend'] not in project.backend_options(target, 'Test'):
            raise ValueError(target + ': the declared validation host is unavailable; no hosted fallback was selected.')
    if 'github' in destinations and not re.fullmatch(r'v\d+\.\d+\.\d+-(?:alpha\.\d+|beta\.\d+|main\.\d+)', release_tag):
        raise ValueError('Choose an unused GitHub release tag such as v1.2.3-alpha.1.')
    from Scripts.build_retention import clean
    try:
        clean(project.root, apply=True)
    except (OSError, RuntimeError) as error:
        print('Build retention incomplete: ' + str(error), flush=True)
    context = capture(project, revision)
    source = context.source(project, revision)
    if delivery and source['dirty']:
        raise ValueError('Delivery requires committed source. Select a committed revision or commit your intended edits.')
    values = source['effective_settings']['values']
    if delivery and 'linux' in targets and values.get('vm.linux_scope') != 'both' and sys.platform == 'darwin':
        raise ValueError('Coordinated Linux delivery requires both declared Linux distributions, not partial coverage.')
    if 'github' in destinations:
        from Scripts.build_snapshots import git
        if git(project.root, 'status', '--porcelain') or git(project.root, 'rev-parse', 'HEAD') != source['logistics_commit']:
            raise ValueError('GitHub publication uses the current clean checkout. Commit intended changes and select its HEAD before planning a release.')
    if any(name in destinations for name in ('firebase', 'testflight')) and sys.platform != 'darwin':
        raise ValueError('Local tester preparation currently requires the configured macOS signing/build host.')

    phases, gates, locks, resources, capacities = [], {}, set(), {}, {}
    branch_sources, evidence = {}, {}
    previous_mobile = None
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
        plan = project.make_plan('Test', target, row['backend'], revision=revision,
            include_ipad=delivery and target == 'ios', _context=context,
            _release_validation=delivery and mobile)
        retain(plan)
        branch_sources[target] = plan.source
        barrier = ()
        if mobile and previous_mobile:
            admission = Phase(target + '.admit-validation', (str(project.interpreter), '-c', 'pass'), str(project.root),
                dependencies=(previous_mobile,), always=True, kind='setup', effect='inspect')
            phases.append(admission)
            barrier = (admission.id,)
        branch = _namespace(plan, target + '.validation', barrier)
        if any(phase.effect in EXTERNAL for phase in branch):
            raise ValueError('Validation cannot dispatch or deliver anything; choose an explicitly available native host.')
        phases.extend(branch)
        gate = Phase(target + '.validated', (str(project.interpreter), '-c', 'pass'), str(project.root),
            dependencies=tuple(phase.id for phase in branch), effect='test')
        phases.append(gate)
        gates[target] = [gate.id]
        if mobile:
            previous_mobile = gate.id
    all_gates = tuple(step for steps in gates.values() for step in steps)

    for name in destinations:
        if name == 'github':
            plan = project.make_plan('Release', targets[0], 'GitHub', revision=revision,
                                     release_tag=release_tag, _context=context)
            retain(plan)
            branch = _namespace(plan, 'github.delivery')
            branch = [replace(phase, dependencies=tuple(dict.fromkeys((*phase.dependencies, *all_gates)))) for phase in branch]
            phases.extend(branch)
            evidence[name] = dict(identity=values['github.repository'] + ' · ' + release_tag +
                ' · commit ' + source['logistics_commit'] + ' · pushes shared/app source and tag; hosted release ZIP (separate from local tester packages)',
                steps=[phase.id for phase in branch if phase.effect in EXTERNAL])
            continue
        target, operation, provider = ('ios', 'Prepare TestFlight', 'testflight') if name == 'testflight' else ('android', 'Prepare Firebase', 'firebase')
        plan = project.make_plan(operation, target, 'This Mac', revision=revision,
                                 build_override=build_override, _context=context)
        retain(plan)
        preparation = _namespace(plan, target + '.preparation', all_gates)
        if any(phase.effect in EXTERNAL for phase in preparation):
            raise ValueError('Tester preparation must stop before upload.')
        phases.extend(preparation)
        output = preparation[-1]
        report = Path(output.artifacts[0])
        receipt = report.with_name(report.stem + '-distribution.json')
        upload = Phase(name + '.upload', (output.argv[0], '-m', 'Scripts.distribute_prepared',
            '--report', str(report), '--receipt', str(receipt)), output.cwd, timeout=14400,
            dependencies=(*all_gates, *(phase.id for phase in preparation)), environment=dict(output.environment),
            kind='distribution', effect='upload', provider=provider, artifacts=(str(receipt),),
            resources={'provider.destination:' + provider + ':Logistics': 1})
        phases.append(upload)
        identity = (str(values['testflight.app_id']) + ' · ' + values['testflight.external_group']
                    if name == 'testflight' else values['firebase.app_id'] + ' · ' + values['firebase.group'])
        evidence[name] = dict(identity=provider + ' · app ' + identity + ' · version ' + source['app_version'], steps=[upload.id])

    # Refuse changes during preparation, including changing selected settings.
    final = capture(project, revision).source(project, revision)
    if final != source:
        raise ValueError('Source or effective settings changed during combined planning. Prepare a fresh plan.')
    # Preparation-only work is intentionally not an external effect. All deliveries
    # carry explicit effects and retain the existing session/artifact-scoped review.
    workspace = project.private / 'workspaces' / 'journeys' / uuid4().hex
    secrets = tuple(dict.fromkeys(secret for plan in plans for secret in plan.secret_environment))
    result = Plan('Logistics', 'Validate and deliver' if delivery else 'Validate selected platforms',
        dict(source, platform_plans=branch_sources), tuple(phases), str(workspace),
        backend='Declared native hosts', max_workers=4, capacities=capacities, resources=resources,
        resource_locks=tuple(sorted(locks)), secret_environment=secrets,
        journey=dict(schema=1, goal=selected['goal'], platforms=gates, destinations=evidence))
    validate_plan(result, selected)
    return result
