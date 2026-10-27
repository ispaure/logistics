"""Logistics adapter for the reusable manager; suites and app policy live here."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import signal
import shutil
import subprocess
import sys
import time
from threading import Event
from uuid import uuid4

try:
    from build_manager import Phase, Plan
    from build_manager.identity import API_VERSION
    if API_VERSION != 1:
        raise ImportError('Unsupported manager adapter API')
except ImportError as error:
    raise RuntimeError('Install the external build-deployment-manager into this project environment '
                       'with python -m pip install --no-deps -e /path/to/build-deployment-manager/Python; '
                       'adapter API 1 is required.') from error
from mobile_build.deployment import manager_settings
from Scripts.build_snapshots import git, identity, materialize
from Scripts.validation_plans import desktop_checks


class LogisticsProject:
    secret_environment = ('GH_TOKEN', 'GITHUB_TOKEN', 'FIREBASE_TOKEN')
    run_options = {'include_ipad': dict(label='Include iPad independent-window coverage in the sequential local run', default=False)}
    platforms = ('macos', 'linux', 'windows', 'ios', 'android')
    operations = ('Test', 'Build', 'Prepare TestFlight', 'Prepare Firebase', 'Reviewed TestFlight workflow', 'Reviewed Firebase workflow', 'Release')
    description = 'Select source, platform and execution location; inspect the ordered plan before running.'

    def __init__(self, root):
        self.root = Path(root).resolve()
        descriptor = self.root / 'build-project.json'
        metadata = json.loads(descriptor.read_text()) if descriptor.is_file() else {}
        self.test_suites = metadata.get('test_suites', [])
        self.run_fields = metadata.get('run_fields', [])
        try:
            from build_manager.journeys import for_host
        except ImportError:
            # Keep API-1 single-platform operations usable with the published pin.
            self.journey_capability = None
        else:
            self.journey_capability = for_host(metadata.get('journey'))
        self.mobile = self.root / 'mobile_build'
        self.interpreter = self.root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        self.runner_directory = self.root
        self.private = self.mobile / '.tools/build-manager'
        self.results_directory = self.root / 'test-results/build-manager'

    def backend_options(self, target, operation='Test'):
        host={'darwin':'macos','linux':'linux','win32':'windows'}.get(sys.platform)
        label={'macos':'This Mac','linux':'This Linux host','windows':'This Windows host'}.get(host,'Unsupported host')
        if target=='ios' and operation=='Test':
            return (('This Mac — iOS Simulators', 'GitHub') if host=='macos' else ('GitHub',))
        if target=='android' and operation=='Test':
            return (label+' — Android Emulator','GitHub')
        if target==host:return (label,'GitHub')
        if target in ('linux','windows') and host=='macos':return ('Local Parallels VM','GitHub')
        return ((label,'GitHub') if target=='android' else ('This Mac','GitHub') if target=='ios' and host=='macos' else ('GitHub',))

    def operations_for(self, target):
        if target in ('macos','linux','windows'):return ('Test','Release')
        if target=='ios':return ('Test','Prepare TestFlight','Reviewed TestFlight workflow','Release')
        return ('Test','Build','Prepare Firebase','Reviewed Firebase workflow','Release')

    def settings_view(self):
        values, sources = manager_settings.settings(self.mobile)
        rows = {}
        reserved = {'vm.shared_host', 'vm.shared_guest'}
        guarded = {'testflight.app_id', 'testflight.bundle_id', 'firebase.bundle_id',
                   'github.token_environment'}
        for name, value in values.items():
            kind = ('bool' if isinstance(value, bool) else
                    'int' if isinstance(value, int) else
                    'directory' if name in {'tools.xcode', 'tools.android_sdk', 'tools.java', 'tools.manager_checkout', 'vm.shared_host'} else
                    'reference' if name.endswith('reference') or name.startswith('signing.') or name.endswith('_python') else 'text')
            rows[name] = dict(value=value, origin=sources[name], kind=kind, read_only=name in guarded or name in reserved)
            if name in reserved:
                rows[name]['origin'] += '; legacy reserved field, not used by isolated local backends'
            if name == 'android.avd':
                rows[name]['label'] = 'Legacy AVD name — leave empty for disposable emulators'
                rows[name]['origin'] += '; unsupported existing-AVD selection; clear this legacy value'
        rows['config.profile'] = dict(value=str(manager_settings.profile_path(self.mobile)),
            origin='local configuration file', read_only=True, section='Local settings',
            label='Private project settings file',
            description='Save writes project settings here. The manager uses its private application configuration directory; this file is not tracked in the project repository.')
        rows['app.version'] = dict(value=manager_settings.app_version(self.mobile),
                                  origin='tracked pyproject.toml; intentional source edit required', read_only=True)
        config = self.mobile / '.device.json'
        team = json.loads(config.read_text()).get('team_id', 'not configured') if config.exists() else 'not configured'
        rows['signing.team'] = dict(value=team, origin='existing pinned device/signing configuration', read_only=True)
        reference = Path(values['auth.testflight_reference'])
        rows['auth.reference_status'] = dict(value='configured' if reference.is_file() else 'missing',
                                              origin='file availability; connection is verified separately', read_only=True)
        rows['build.uniqueness'] = dict(value='Local reservations are locked. Other machines require provider verification.',
                                       origin='local allocator limitation', read_only=True)
        from mobile_build.deployment.testflight_deploy import next_build
        from mobile_build.deployment.firebase_deploy import next_build as next_android
        rows['build.next_ios'] = dict(value=next_build(self.mobile), origin='preview only; reserved at build start', read_only=True)
        rows['build.next_android'] = dict(value=next_android(self.mobile, self.mobile / '.android-beta'), origin='preview only; reserved at build start', read_only=True)
        rows['github.credentials'] = dict(value='Hosted workflows use repository secrets/variables; local file references are not synced.',
                                           origin='provider boundary', read_only=True)
        from build_manager.providers import settings_rows
        from build_manager.hosts import capabilities
        rows.update(settings_rows(self.platforms))
        for capability in capabilities(self.platforms,hosted=self.platforms):
            rows['host.'+capability['location']+'.'+capability['target']] = dict(
                value=capability['status']+' — '+capability['reason'],origin='explicit host/target capability policy',
                read_only=True,section='Host capabilities',description=capability['reason'],
                label=capability['target']+' — '+capability['location'])
        from mobile_build.deployment.settings_help import describe_settings
        return describe_settings(rows)

    def storage_inventory(self):
        from Scripts.build_retention import storage_inventory
        return storage_inventory(self.root)

    def delete_storage(self, selections):
        from Scripts.build_retention import delete_storage
        return delete_storage(self.root, selections)

    def run_defaults(self, *, cancelled=lambda:False):
        rows=self.settings_view()
        defaults = {field['id']:rows[field['id']]['value'] for field in self.run_fields if field['id'] in rows}
        ios = rows['testflight.what_to_test']['value']
        android = rows['firebase.release_notes']['value']
        defaults['testers.message'] = ios if ios == android else ''
        return defaults

    def save_settings(self, values):
        manager_settings.save(self.mobile, values)

    def set_app_version(self, value):
        manager_settings.set_app_version(self.mobile, value)

    def make_journey(self, goal, platforms, destinations, **options):
        if self.journey_capability is None:
            raise RuntimeError('Install the reviewed local build-deployment-manager with journey schema 1 to use combined workflows; legacy single-platform operations remain available.')
        from Scripts.manager_journeys import make_journey
        return make_journey(self, dict(schema=1, goal=goal, platforms=platforms, destinations=destinations), **options)

    def make_plan(self, operation, target, backend, **options):
        from dataclasses import replace
        started = time.monotonic()
        from Scripts.manager_suites import selection, with_reports, with_host_gates, acceptance_phase
        run_overrides = options.pop('run_overrides', None)
        if run_overrides:
            from Scripts.manager_journeys import capture
            if options.get('_context') is not None:
                raise ValueError('Cannot replace captured settings inside a workflow.')
            options['_context'] = capture(self, options.get('revision','working-tree'), run_overrides)
        suite = options.pop('suite', '')
        release_validation = options.pop('_release_validation', False)
        selection(self.root, suite, operation, target, backend, options.get('pattern', ''))
        workflow = operation in ('Reviewed TestFlight workflow','Reviewed Firebase workflow')
        requested_operation = operation
        if workflow:
            operation = 'Prepare TestFlight' if operation == 'Reviewed TestFlight workflow' else 'Prepare Firebase'
        from Scripts.build_retention import clean
        try:
            if options.get('_context') is None:
                clean(self.root, apply=True)
        except (OSError, RuntimeError) as error:
            print('Build retention incomplete: ' + str(error), flush=True)
        plan = self._make_plan(operation, target, backend, suite=suite, **options)
        if workflow:
            validation_options = dict(options)
            if target == 'ios':
                validation_options['include_ipad'] = True  # Required release inventory, independent of standalone test choices.
            validation = self._make_plan('Test', target, self.backend_options(target, 'Test')[0], **validation_options)
            if any(validation.source.get(key) != plan.source.get(key)
                   for key in ('fingerprint', 'logistics_commit', 'commonUtils_commit')):
                raise ValueError('Native validation and preparation must use the exact same source.')
            host_python = validation.source.get('effective_settings', {}).get('values', {}).get('tools.desktop_python', str(self.interpreter))
            validation = with_host_gates(validation, host_python)
            gate = acceptance_phase(validation, target)
            # Required native/runtime gates and owned cleanup precede signing.
            plan = replace(plan, phases=(*validation.phases, gate,
                *(replace(phase, dependencies=(*phase.dependencies, gate.id)) for phase in plan.phases)))
            preparation = plan.phases[-1]
            report = Path(preparation.artifacts[0])
            receipt = report.with_name(report.stem+'-distribution.json')
            upload = Phase('reviewed-distribution',(preparation.argv[0],'-m','Scripts.distribute_prepared',
                '--report',str(report),'--receipt',str(receipt)),preparation.cwd,timeout=14400,
                dependencies=(preparation.id,),environment=dict(preparation.environment),kind='distribution',
                effect='upload',provider='testflight' if target=='ios' else 'firebase',artifacts=(str(receipt),))
            plan = replace(plan,operation=requested_operation,phases=(*plan.phases,upload))
        elif release_validation:
            if target not in {'ios', 'android'} or operation != 'Test':
                raise ValueError('Release validation applies only to complete mobile tests.')
            host_python = plan.source['effective_settings']['values']['tools.desktop_python']
            plan = with_host_gates(plan, host_python)
            gate = acceptance_phase(plan, target)
            plan = replace(plan, phases=(*plan.phases, gate))
        elif target in {'ios', 'android'} and operation == 'Test' and not suite and not options.get('pattern') and backend != 'GitHub':
            host_python = plan.source.get('effective_settings', {}).get('values', {}).get('tools.desktop_python', str(self.interpreter))
            plan = with_host_gates(plan, host_python)
        if suite == 'android.native':
            plan = replace(plan, phases=tuple(replace(phase, dependencies=tuple(name for name in phase.dependencies if name != 'android-runtime-tools'))
                for phase in plan.phases if phase.id not in {'android-runtime','android-runtime-tools'}))
        elif suite == 'android.runtime':
            plan = replace(plan, phases=tuple(replace(phase, dependencies=tuple(name for name in phase.dependencies if name != 'android-build'))
                for phase in plan.phases if phase.id not in {'android-native','android-build'}))
        if suite in {'ios.native', 'ios.runtime'}:
            core = {'ios-runtime-tools', 'ios-runtime', 'ios-runtime-cleanup'}
            kept = tuple(phase for phase in plan.phases if (phase.id in core) == (suite == 'ios.runtime'))
            names = {phase.id for phase in kept}
            plan = replace(plan, phases=tuple(replace(phase, dependencies=tuple(name for name in phase.dependencies if name in names)) for phase in kept))
        if suite:
            plan = replace(plan, source=dict(plan.source, test_suite=suite))
        if options.get('pattern'):
            plan = replace(plan, source=dict(plan.source, focused_test_pattern=options['pattern']))
        plan = with_reports(plan, target)
        snapshot = self.private / 'snapshots' / plan.source.get('fingerprint', '')
        resources = (str(snapshot.with_suffix('.lock')),) if (snapshot / '.manager-source.json').is_file() else ()
        plan = declare_resources(plan,target)
        settings_snapshot = plan.source.get('effective_settings')
        phases = plan.phases
        if settings_snapshot:
            from build_manager.profiles import save_profile
            reference = Path(plan.workspace) / 'settings' / (uuid4().hex + '.json')
            save_profile(reference, settings_snapshot['values'], allowed=manager_settings.defaults(self.mobile))
            phases = tuple(replace(phase, environment=dict(phase.environment,
                LOGISTICS_MANAGER_PROFILE=str(reference), LOGISTICS_MANAGER_ACCOUNT_DEFAULTS='{}')) for phase in phases)
        secrets=plan.secret_environment
        if settings_snapshot:
            reference=settings_snapshot['values'].get('auth.github_reference','')
            if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',reference):secrets=tuple(dict.fromkeys((*secrets,reference)))
        values=settings_snapshot['values'] if settings_snapshot else {}
        destination=(values.get('github.repository','declared GitHub repository') if plan.backend=='GitHub' else
            {'app':values.get('testflight.app_id'),'group':values.get('testflight.external_group')} if operation=='Prepare TestFlight' else
            {'app':values.get('firebase.app_id'),'group':values.get('firebase.group')} if operation=='Prepare Firebase' else
            'local '+target+' workspace')
        plan = replace(plan, phases=phases, secret_environment=secrets, resource_locks=(*plan.resource_locks,*resources),
                       source=dict(plan.source,destination=destination,plan_preparation_seconds=time.monotonic()-started))
        from Scripts.test_evidence import with_reuse
        return with_reuse(plan)

    def _make_plan(self, operation, target, backend, *, revision='working-tree', pattern='', build_override='', include_ipad=False, release_tag='', suite='', _context=None):
        if operation not in self.operations or target not in self.platforms or backend not in self.backend_options(target, operation):
            raise ValueError('Unsupported operation/platform/backend selection.')
        if pattern and (not pattern.endswith('.py') or '/' in pattern or '\\' in pattern):
            raise ValueError('Use a focused test filename/glob, not a path or command.')
        if _context is None:
            source = identity(self.root, revision)
            source.update(host=platform.platform(), architecture=platform.machine())
            source['app_version'] = manager_settings.app_version(self.mobile,
                revision=None if revision == 'working-tree' else source['logistics_commit'])
            options, origins = manager_settings.settings(self.mobile)
            source['effective_settings'] = dict(values=options, origins=origins)
        else:
            from Scripts.manager_journeys import PlanningContext
            if not isinstance(_context, PlanningContext):
                raise ValueError('Invalid internal planning context.')
            source = _context.source(self, revision)
            options = dict(source['effective_settings']['values'])
            origins = dict(source['effective_settings']['origins'])
        workspace = self.private / 'workspaces' / target
        if backend == 'GitHub':
            return self.github_plan(operation, target, source, workspace, options, revision, release_tag)
        if operation == 'Release':
            raise ValueError('Choose GitHub for a release; tests do not publish automatically.')
        if target in ('linux', 'windows') and backend == 'Local Parallels VM':
            return self.local_vm_plan(operation, target, source, workspace, options, pattern)
        if target in ('macos','linux','windows'):
            expected_system={'macos':'Darwin','linux':'Linux','windows':'Windows'}[target]
            from build_manager.local import inspect_python
            source['toolchain'] = inspect_python(options['tools.desktop_python'], ('Pillow', 'PySide6', 'pyzipper', 'yt-dlp'))
            if source['toolchain']['system'] != expected_system:
                raise ValueError('The selected interpreter does not run on the requested native host; no fallback was selected.')
        snapshot = self.private / 'snapshots' / source['fingerprint']
        materialize(self.root, snapshot, revision, expected=source)
        env = dict(PYTHONPATH=os.pathsep.join((str(snapshot), str(snapshot / 'Python'))),
                   QT_QPA_PLATFORM='offscreen', PYTHONUNBUFFERED='1',
                   LOGISTICS_MANAGER_ACCOUNT_DEFAULTS=os.environ.get('LOGISTICS_MANAGER_ACCOUNT_DEFAULTS', '{}'))
        python = options['tools.desktop_python']
        if target in ('macos','linux','windows'):
            if platform.system() != expected_system:
                raise ValueError('Requested native target is unsupported on this host; no fallback was selected.')
            if operation != 'Test':
                raise ValueError('Desktop Build is not implemented by the existing source-package workflow; select Test or GitHub release.')
            commands = [('focused', ['dev.py', 'test', 'desktop', pattern, '--python', python], 600)] if pattern else desktop_checks(expected_system, workspace / 'reports', snapshot)
            if suite in {'portable.contracts', 'desktop.ui'}:
                directory = 'Python/tests/tooling' if suite == 'portable.contracts' else 'Python/tests/application'
                commands = [(suite, ['Python/tests/run_regressions.py', directory, '--isolate-modules',
                                     '--pattern', pattern or 'test*.py'], 900)]
            if not pattern and not suite:
                commands += [('release-tooling', ['-m', 'unittest', 'discover', '-s', '.github/scripts', '-p', 'test_*.py'], 300)]
            env['LOGISTICS_REQUIRE_LOCALCRYPT_TESTS'] = '1'
            prerequisites = Phase('environment', (python, '-m', 'Scripts.local_desktop'), str(snapshot),
                                  timeout=180, environment=env, kind='setup')
            from build_manager.test_manifest import discover as discover_tests
            test_dependencies = {row['id']: tuple(row['after']) for row in discover_tests(snapshot, 'desktop')} if not pattern and not suite else {}
            phases = (prerequisites,) + tuple(Phase(name, (python, *arguments), str(snapshot), timeout=timeout,
                                 environment=env, dependencies=('environment', *test_dependencies.get(name, ()))) for name, arguments, timeout in commands)
            return Plan('Logistics', operation, source, phases, str(workspace), backend=backend)
        if operation == 'Test' and target == 'ios' and suite == 'ios.runtime':
            return self.ios_simulator_plan(source, snapshot, workspace, options, env, pattern, False, runtime_only=True)
        return self.mobile_plan(operation, target, source, snapshot, workspace, options, env,
                                pattern, build_override, include_ipad)

    def github_plan(self, operation, target, source, workspace, options, revision, release_tag):
        if revision == 'working-tree' and source['dirty']:
            raise ValueError('GitHub cannot run uncommitted source. Select an explicitly published revision.')
        if operation == 'Release':
            if not release_tag:
                from Scripts.release_naming import suggest_tag, source_version
                release_tag = suggest_tag(self.root, source_version(self.root, source['logistics_commit']))
            if not re.fullmatch(r'v\d+\.\d+\.\d+-(?:alpha\.\d+|beta\.\d+|main\.\d+)', release_tag):
                raise ValueError('Choose an explicit release channel/tag, separate from app version and mobile build numbers.')
            command = (str(self.interpreter), '-m', 'Scripts.build_project', 'release', '--tag', release_tag,
                       '--commit', source['logistics_commit'], '--root', str(self.root))
            return Plan('Logistics', operation, dict(source, release_tag=release_tag),
                        (Phase('release-source-and-gates', command, str(self.root), timeout=14400),),
                        str(workspace), backend='GitHub', effect='publish')
        if operation not in ('Test', 'Build'):
            raise ValueError('Tester preparation uses the local verified signing/build tools, not a generic hosted dispatch.')
        ref = git(self.root, 'branch', '--show-current') if revision in ('working-tree', 'HEAD') else revision
        if not ref:
            raise ValueError('Choose a published branch or tag for hosted validation.')
        selected = [('native', 'mobile-build.yml'), ('runtime', 'mobile-runtime.yml')] if target in ('ios', 'android') else [('desktop-matrix', 'archive-platform-checks.yml')]
        source['hosted_coverage'] = target
        phases = []
        for name, workflow in selected:
            receipt = workspace / 'remote' / (uuid4().hex + '.json')
            command = (str(self.interpreter), '-m', 'Scripts.build_project', 'github', '--operation-receipt', str(receipt), '--platform', target,
                       '--workflow', workflow, '--ref', ref, '--commit', source['logistics_commit'], '--root', str(self.root))
            phases.append(Phase('github-' + name, command, str(self.root), timeout=14400, artifacts=(str(receipt),),effect='dispatch',kind='validation-dispatch'))
        return Plan('Logistics', operation, source, tuple(phases),
                    str(workspace), backend='GitHub', effect='dispatch')

    def local_vm_plan(self, operation, target, source, workspace, options, pattern):
        if target == 'windows':
            return self.windows_vm_plan(operation, source, workspace, options, pattern)
        if operation != 'Test':
            raise ValueError('This Linux backend accepts Test plans; no Build operation is implied.')
        from build_manager.parallels import Parallels
        client = Parallels()
        if options['vm.fedora_mode'] not in ('guest', 'container-on-ubuntu'):
            raise ValueError('Choose an explicit supported Fedora backend mode.')
        selector = options['vm.fedora_container_host'] if options['vm.fedora_mode'] == 'container-on-ubuntu' else options['vm.fedora']
        if not selector:
            raise ValueError('No Fedora test machine is configured. Open Setup → Test machines to create or recover the dedicated Linux machine, then reopen Project settings and Save. Container mode requires its own explicit host.')
        guest = client.selected(selector)
        snapshot = self.private / 'snapshots' / source['fingerprint']
        materialize(self.root, snapshot, source['selection'], expected=source)
        results = workspace / ('fedora-' + uuid4().hex)
        command = (str(self.interpreter), '-m', 'Scripts.vm_backend', '--vm', guest['uuid'],
            '--snapshot', str(snapshot), '--results', str(results), '--distribution', 'fedora',
            '--source-identity', json.dumps(source))
        if options['vm.fedora_mode'] == 'container-on-ubuntu':
            command += ('--container-image', 'localhost/logistics-fedora-tests:43')
        if options['tools.manager_checkout']:
            command += ('--manager-checkout', options['tools.manager_checkout'])
        if options['vm.shutdown_after_run']:
            command += ('--shutdown',)
        if pattern:
            command += ('--pattern', pattern)
        phases = (Phase('fedora', command, str(snapshot), timeout=5400, stop_grace=240,
                        artifacts=(str(results / 'result.json'),)),)
        source['selected_guests'] = [{'distribution': 'fedora', 'name': guest['name'],
                                      'uuid': guest['uuid'], 'initial_state': guest['status']}]
        source['linux_coverage'] = 'fedora'
        source['fedora_mode'] = options['vm.fedora_mode']
        source['focused_pattern'] = pattern
        return Plan('Logistics', 'Local Linux tests (Fedora)', source, tuple(phases), str(workspace),
                    backend='Local Parallels VM')

    def windows_vm_plan(self, operation, source, workspace, options, pattern):
        if operation != 'Test':
            raise ValueError('Windows guest supports Test plans; no Build operation is implied.')
        from build_manager.parallels import Parallels
        if not options['vm.windows']:
            raise ValueError('No Windows test machine is configured. Open Setup → Test machines to create or recover the dedicated Windows machine, then reopen Project settings and Save.')
        guest = Parallels().selected(options['vm.windows'])
        snapshot = self.private / 'snapshots' / source['fingerprint']
        materialize(self.root, snapshot, source['selection'], expected=source)
        results = workspace / ('windows-' + uuid4().hex)
        command = (str(self.interpreter), '-m', 'Scripts.windows_backend', '--vm', guest['uuid'],
                   '--snapshot', str(snapshot), '--results', str(results), '--source-identity', json.dumps(source))
        if options['tools.manager_checkout']:
            command += ('--manager-checkout', options['tools.manager_checkout'])
        prepared = options['vm.windows_prepared_reference']
        if prepared:
            command += ('--prepared', prepared)
        if pattern:
            command += ('--pattern', pattern)
        if options['vm.shutdown_after_run']:
            command += ('--shutdown',)
        source.update(selected_guest=guest, focused_pattern=pattern)
        return Plan('Logistics', 'Focused Windows contracts' if pattern else 'Complete local Windows tests', source,
                    (Phase('windows', command, str(snapshot), timeout=7200, stop_grace=240, artifacts=(str(results / 'result.json'),)),),
                    str(workspace), backend='Local Parallels VM')

    def android_emulator_plan(self, operation, source, snapshot, workspace, options, env, pattern):
        from build_manager.hosts import android_abi, android_acceleration
        abi=android_abi()
        if operation=='Test' and (platform.system()!='Darwin' or abi!='arm64-v8a'):
            raise ValueError('Logistics CPython Android runtime suite currently requires macOS ARM; the generic transport is portable but this project compiler is unavailable on this host.')
        if pattern:
            raise ValueError('Native/runtime Android acceptance uses the complete declared suites, not host filename filters.')
        if options['android.avd']:
            raise ValueError('Existing AVD state is preserved. Configure the disposable image/model instead of an existing AVD name.')
        from build_manager.android_emulators import AndroidEmulator
        sdk = Path(options['tools.android_sdk'])
        java = Path(options['tools.java'])
        if not options['tools.android_sdk'] or not options['tools.java'] or not (java/'bin/java').is_file():
            raise ValueError('Configure an explicit complete Android SDK and Java17 JDK in Settings.')
        env = dict(env, ANDROID_HOME=str(sdk), ANDROID_SDK_ROOT=str(sdk), JAVA_HOME=str(java),
                   PATH=str(self.mobile/'.tools/go/bin')+os.pathsep+os.environ.get('PATH',''),
                   PIP_FIND_LINKS=str(self.mobile/'.tools/release-wheels'), GRADLE_OPTS='-Dorg.gradle.daemon=false')
        if options['tools.xcode']:
            env['DEVELOPER_DIR'] = options['tools.xcode']
        run = workspace/('emulator-'+uuid4().hex)
        device = run/'device'
        python = options['tools.mobile_python']
        base = (python,'-m','Scripts.android_backend')
        common = ('--root',str(snapshot),'--workspace',str(device))
        phases = [Phase('android-build',(*base,'build',*common,'--result',str(run/'build.json')),str(snapshot),
                        timeout=3600,environment=env,kind='build',artifacts=(str(run/'build.json'),))]
        source = dict(source, sdk=str(sdk),java=str(java),abi=abi,image=options['android.image'],
                      device_lifecycle='owned disposable accelerated ARM AVD; preserve physical and existing emulator data')
        if operation=='Test':
            source['acceleration'] = AndroidEmulator(sdk,device,environment=env).inspect(options['android.image'], acceleration=android_acceleration())
            pin = json.loads((self.root/'Scripts/mobile_runtime_tools.json').read_text())['cpython']
            cache = self.private/('cpython-'+pin['revision'])
            phases += [Phase('android-runtime-tools',(python,'-m','Scripts.mobile_runtime','prepare','--cache',str(cache),
                                '--result',str(run/'runtime-prepared.json')),str(snapshot),timeout=5400,environment=env,kind='setup',
                                artifacts=(str(run/'runtime-prepared.json'),)),
                       Phase('android-ready',(*base,'ready',*common,'--image',options['android.image'],'--model',options['android.model'],
                                '--result',str(run/'ready.json')),str(snapshot),timeout=360,environment=env,kind='setup',
                                dependencies=('android-build','android-runtime-tools'),artifacts=(str(run/'ready.json'),))]
            for action in ('native','runtime'):
                report = run/(action+'.json')
                phases.append(Phase('android-'+action,(*base,action,*common,'--runtime-cache',str(cache),'--result',str(report)),
                    str(snapshot),timeout=2500 if action=='native' else 1900,environment=env,dependencies=('android-ready',),artifacts=(str(report),)))
            phases.append(Phase('android-cleanup',(*base,'cleanup',*common),str(snapshot),timeout=180,environment=env,always=True,kind='cleanup'))
        return Plan('Logistics','Complete Android native and runtime validation' if operation=='Test' else 'Build native Android test APK; no install',
                    source,tuple(phases),str(workspace),backend=self.backend_options('android','Test')[0],effect='test' if operation=='Test' else 'build')

    def ios_simulator_plan(self, source, snapshot, workspace, options, env, pattern, include_ipad, *, runtime_only=False):
        if sys.platform != 'darwin':
            raise ValueError('Local iOS simulator validation requires macOS.')
        if pattern:
            raise ValueError('Native iOS acceptance runs the canonical complete native plan; filename filters apply to host contracts.')
        from build_manager.apple_simulators import AppleSimulators
        from mobile_build.validation.ui_tools import select_ios_device
        env = dict(env)
        if options['tools.xcode']:
            env['DEVELOPER_DIR'] = options['tools.xcode']
        env.update(PATH=str(self.mobile/'.tools/go/bin')+os.pathsep+os.environ.get('PATH',''),
                   PIP_FIND_LINKS=str(self.mobile/'.tools/release-wheels'))
        client = AppleSimulators(env)
        inventory = client.devices()['devices']
        selected = []
        kinds = ('iphone',) if runtime_only else ('iphone', 'duo', 'ipad') if include_ipad else ('iphone', 'duo')
        for kind in kinds:
            configured = options['ios.'+kind]
            rows = [(runtime, row) for runtime, devices in inventory.items() for row in devices
                    if row.get('isAvailable') and (not configured or configured in (row['udid'], row['name']))]
            candidate = select_ios_device({'devices': {runtime: [row for rt,row in rows if rt == runtime] for runtime,_ in rows}}, ipad=kind=='ipad', duo=kind=='duo')
            matches = [(runtime,row) for runtime,row in rows if row['udid']==candidate]
            runtime, row = matches[0]
            model = row.get('deviceTypeIdentifier')
            if not model:
                raise ValueError('Selected simulator lacks an explicit device model.')
            selected.append(dict(kind=kind, model=model, runtime=runtime, template=row['udid']))
        source = dict(source, simulator_toolchain=client.toolchain(), simulator_sequence=selected, device_lifecycle='create owned disposable simulator; delete after evidence')
        run = workspace / ('simulators-' + uuid4().hex)
        python = options['tools.mobile_python']
        base = (python, '-m', 'Scripts.ios_backend')
        build_report = run/'build.json'
        phases = [Phase('ios-build', (*base,'build','--root',str(snapshot),'--result',str(build_report)), str(snapshot),
                        timeout=3600, environment=env, kind='build', artifacts=(str(build_report),))]
        previous_cleanup = None
        for row in selected:
            kind = row['kind']
            report = run/kind/'result.json'
            lease = run/(kind+'-lease.json')
            phases.append(Phase(kind, (*base,'test','--root',str(snapshot),'--kind',kind,'--model',row['model'],
                          '--runtime',row['runtime'],'--lease',str(lease),'--result',str(report)), str(snapshot),
                          timeout=2100, environment=env, dependencies=(previous_cleanup or 'ios-build',), artifacts=(str(report),)))
            phases.append(Phase(kind+'-cleanup', (*base,'cleanup','--root',str(snapshot),'--lease',str(lease)), str(snapshot),
                          timeout=180, environment=env, always=True, kind='cleanup', dependencies=(kind,)))
            previous_cleanup = kind+'-cleanup'
        pin = json.loads((self.root / 'Scripts/mobile_runtime_tools.json').read_text())['cpython']
        cache = self.private / ('cpython-ios-' + pin['revision'])
        core = (python, '-m', 'Scripts.ios_runtime')
        lease = run / 'runtime-lease.json'
        report = run / 'runtime' / 'result.json'
        phases.extend([
            Phase('ios-runtime-tools', (*core, 'prepare', '--cache', str(cache), '--result', str(run / 'runtime-prepared.json')),
                  str(snapshot), timeout=5400, environment=env, kind='setup', artifacts=(str(run / 'runtime-prepared.json'),)),
            Phase('ios-runtime', (*core, 'test', '--root', str(snapshot), '--cache', str(cache), '--model', selected[0]['model'],
                  '--runtime', selected[0]['runtime'], '--lease', str(lease), '--result', str(report)), str(snapshot), timeout=1500,
                  environment=env, dependencies=('ios-runtime-tools', previous_cleanup), artifacts=(str(report), str(report.with_suffix('.log')), str(report.with_suffix('.raw.log')))),
            Phase('ios-runtime-cleanup', (*core, 'cleanup', '--lease', str(lease)), str(snapshot), timeout=180,
                  environment=env, always=True, kind='cleanup', dependencies=('ios-runtime',))])
        source = dict(source, ios_core_runtime=dict(revision=pin['revision'], version=pin['version'],
                      architecture='arm64', lifecycle='owned disposable simulator; adapted clone preserves pinned interpreter and core inventory'))
        return Plan('Logistics', 'Complete iOS native and runtime validation', source, tuple(phases), str(workspace),
                    backend='This Mac — iOS Simulators')

    def mobile_plan(self, operation, target, source, snapshot, workspace, options, env, pattern, build_override, include_ipad):
        if operation in ('Test','Build') and target == 'android':
            return self.android_emulator_plan(operation, source, snapshot, workspace, options, env, pattern)
        if operation == 'Test' and target == 'ios':
            return self.ios_simulator_plan(source, snapshot, workspace, options, env, pattern, include_ipad)
        if operation in ('Prepare TestFlight', 'Prepare Firebase'):
            expected = 'ios' if operation == 'Prepare TestFlight' else 'android'
            if target != expected:
                raise ValueError('Choose ' + expected + ' for ' + operation + '.')
            if source['dirty']:
                raise ValueError('Commit the reviewed source before preparing a signed tester artifact.')
            if build_override and not build_override.isdigit():
                raise ValueError('Mobile build override must be numeric.')
            # Link existing protected inputs, never copy keys into source or a
            # profile. Generated builds remain in this source snapshot.
            from Scripts.build_snapshots import PRIVATE_RUNTIME_NAMES
            for name in PRIVATE_RUNTIME_NAMES:
                canonical = self.mobile / name
                destination = snapshot / 'mobile_build' / name
                if canonical.exists() and not destination.exists():
                    destination.symlink_to(canonical, target_is_directory=canonical.is_dir())
            env.update(LOGISTICS_MANAGER_PROFILE=str(manager_settings.profile_path(self.mobile)),
                       LOGISTICS_BUILD_HISTORY=str(self.mobile / 'build'))
            artifact = workspace / 'prepared-artifacts' / (uuid4().hex + '.json')
            env['LOGISTICS_MANAGER_ARTIFACT_REPORT'] = str(artifact)
            if options['tools.xcode']:
                env['DEVELOPER_DIR'] = options['tools.xcode']
            if options['tools.android_sdk']:
                env.update(ANDROID_HOME=options['tools.android_sdk'], ANDROID_SDK_ROOT=options['tools.android_sdk'])
            if options['tools.java']:
                env['JAVA_HOME'] = options['tools.java']
            env['PATH'] = str(self.mobile / '.tools/go/bin') + os.pathsep + os.environ.get('PATH', '')
            env['PIP_FIND_LINKS'] = str(self.mobile / '.tools/release-wheels')
            module = 'testflight_deploy' if target == 'ios' else 'firebase_deploy'
            arguments = ['--prepare-only'] if target == 'ios' else ['--build-only']
            if build_override:
                arguments += ['--build-number' if target == 'ios' else '--version-code', build_override]
            if target == 'ios':
                for key, flag in [('signing.app_profile', '--profile'), ('signing.inbox_profile', '--inbox-profile')]:
                    if options[key]:
                        arguments += [flag, options[key]]
            if target == 'ios':
                state = artifact.with_name(artifact.stem + '-archive.json')
                archive_args = [arg for arg in arguments if arg != '--prepare-only']
                command = (options['tools.mobile_python'], '-m', 'Scripts.manager_packages')
                archive = Phase('build-release-archive', (*command, 'archive', '--state', str(state), *archive_args),
                    str(snapshot), timeout=14400, environment=dict(env), kind='build', effect='build',
                    artifacts=(str(state),), label='Build iOS Release archive',
                    description='Shared compiled archive · device exports use separate provisioning')
                export = Phase('prepare-verified-artifact', (*command, 'export-testflight', '--state', str(state)),
                    str(snapshot), timeout=14400, dependencies=(archive.id,), environment=dict(env),
                    kind='build', effect='build', artifacts=(str(artifact),), label='Export & sign for TestFlight',
                    description='App Store distribution package · no upload')
                return Plan('Logistics', operation, source, (archive, export), str(workspace), backend='This Mac', effect='build')
            phase = Phase('prepare-verified-artifact', (options['tools.mobile_python'], '-m',
                'mobile_build.deployment.' + module, *arguments), str(snapshot), timeout=14400,
                environment=env, kind='build', artifacts=(str(artifact),),
                label='Build & sign Android Release APK', description='One signed APK can serve Firebase and selected Release devices')
            return Plan('Logistics', operation, source, (phase,), str(workspace), backend='This Mac', effect='build')
        raise ValueError('Local mobile backend is not installed yet; no hosted fallback or passing result is implied.')

    def verification_plan(self):
        source = identity(self.root)
        from build_manager.profiles import save_profile
        values, origins = manager_settings.settings(self.mobile)
        reference = self.private / 'verification' / 'settings' / (uuid4().hex + '.json')
        save_profile(reference, values, allowed=manager_settings.defaults(self.mobile))
        source['effective_settings'] = dict(values=values, origins=origins)
        environment = dict(LOGISTICS_MANAGER_PROFILE=str(reference), LOGISTICS_MANAGER_ACCOUNT_DEFAULTS='{}')
        command = (str(self.interpreter), '-m', 'Scripts.build_project', 'verify', '--root', str(self.root))
        return Plan('Logistics', 'Read-only connection verification', source,
                    (Phase('verify-settings', command, str(self.root), timeout=120, kind='inspect', environment=environment),),
                    str(self.private / 'verification'), effect='inspect')


def declare_resources(plan, target):
    """Project policy: lock actual shared build/cache/signing resources per step."""
    from dataclasses import replace
    if plan.backend == 'GitHub':
        return plan
    phases=[]
    for phase in plan.phases:
        requirements=dict(phase.resources)
        if phase.kind=='build' or phase.id in {'android-runtime-tools','ios-runtime-tools'}:
            requirements.update({'host.mobile-build':1,'project.workspace:'+phase.cwd:1})
        if phase.id.startswith('android-'):
            if phase.id in {'android-native','android-runtime','android-ready','android-cleanup'}:
                requirements['android.device-workspace:'+plan.workspace]=1
            else:
                requirements['android.sdk-cache']=1
        if phase.id in {'prepare-verified-artifact', 'build-release-archive'}:requirements['host.signing-keychain']=1
        if phase.effect in {'upload','publish'}:
            requirements['provider.destination:'+phase.provider+':'+plan.project]=1
        phases.append(replace(phase,resources=requirements,stop_grace=5 if target in {'ios','android'} else phase.stop_grace))
    return replace(plan,phases=tuple(phases))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('verify', 'github', 'release'))
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--platform', choices=LogisticsProject.platforms)
    parser.add_argument('--ref')
    parser.add_argument('--commit')
    parser.add_argument('--operation-receipt', type=Path)
    parser.add_argument('--workflow')
    parser.add_argument('--tag')
    args = parser.parse_args()
    if args.command == 'verify':
        values, sources = manager_settings.settings(args.root / 'mobile_build')
        print(json.dumps(dict(status='configuration valid', effective_sources=sources,
                              checked_at=datetime.now(timezone.utc).isoformat())))
        # Providers are verified separately, so a missing authentication method
        # cannot be mislabeled as verified signing or a successful upload.
        from mobile_build.deployment.testflight_external import Client, credentials, settings, target
        target(Client(credentials()), settings())
        from mobile_build.deployment.firebase_deploy import preflight
        firebase = args.root / 'mobile_build/.tools/firebase'
        cli = str(firebase) if firebase.is_file() else shutil.which('firebase')
        if not cli:
            raise ValueError('Firebase CLI is missing; install it before verifying a connection.')
        preflight(cli, allow_login=False)
        print('App Store Connect and Firebase app/group read-only checks passed.')
        github_client(values, args.root).verify()
        print('GitHub repository read access verified; workflow write permission was not exercised.')
        return 0
    values, _ = manager_settings.settings(args.root / 'mobile_build')
    client = github_client(values, args.root)
    cancelled = Event()
    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, lambda *_: cancelled.set())
    if args.command == 'github':
        inputs = {'target': args.platform}
        run = client.dispatch(args.workflow, args.ref, args.commit, inputs, confirmed=True)
        receipt = dict(schema=1, provider='github', run_id=run, repository=values['github.repository'],
                       expected_commit=args.commit, workflow=args.workflow, status='queued',
                       operation_id=os.environ.get('BUILD_MANAGER_OPERATION_ID',''))
        if args.operation_receipt:
            from build_manager.profiles import save_json
            save_json(args.operation_receipt, receipt)
        print(json.dumps(receipt), flush=True)
        result = client.wait(run, args.commit, timeout=13800, cancelled=cancelled,
                             progress=lambda value: print(json.dumps(value), flush=True))
        return int(result.get('status') != 'completed')
    return release_source(args.root, client, args.tag, args.commit, cancelled)


def github_client(values, root):
    from build_manager.github import GitHub, credential_token
    kind=values.get('auth.github_kind','auto')
    reference=values.get('auth.github_reference') or values['github.token_environment']
    if kind=='auto' and values['github.authentication']!='existing git credential helper':kind='environment-name'
    token=credential_token(reference=reference,kind=kind,root=root)
    return GitHub(values['github.repository'],token)


def release_source(root, client, tag, commit, cancelled):
    if not re.fullmatch(r'v\d+\.\d+\.\d+-(?:alpha\.\d+|beta\.\d+|main\.\d+)', tag or ''):
        raise ValueError('Select an explicit supported release tag.')
    if git(root, 'status', '--porcelain') or git(root, 'rev-parse', 'HEAD') != commit:
        raise ValueError('Commit intended source before requesting a release.')
    remote = subprocess.check_output(['git', 'ls-remote', '--tags', 'origin', 'refs/tags/' + tag], cwd=root, text=True, timeout=30)
    if remote.strip():
        raise ValueError('Release tag already exists; it will never be moved.')
    shared = root / 'Python/commonUtils'
    if git(shared, 'status', '--porcelain'):
        raise ValueError('Commit intended shared changes first.')
    branch = git(shared, 'branch', '--show-current')
    if not branch:
        raise ValueError('Select the intended commonUtils publication branch before releasing.')
    subprocess.run(['git', 'push', 'origin', branch], cwd=shared, check=True, timeout=120)
    channel = tag.split('-')[1].split('.')[0]
    subprocess.run(['git', 'push', 'origin', commit + ':refs/heads/' + channel], cwd=root, check=True, timeout=120)
    subprocess.run(['git', 'tag', tag, commit], cwd=root, check=True, timeout=30)
    subprocess.run(['git', 'push', 'origin', 'refs/tags/' + tag], cwd=root, check=True, timeout=120)
    # Tag pushes start the gated publication workflow. Dispatching another run
    # would duplicate the matrix and a manual run does not publish an asset.
    import time
    deadline = time.monotonic() + 120
    run = None
    while time.monotonic() < deadline and not cancelled.is_set():
        response = client.request('GET', client.base + '/actions/runs?event=push&head_sha=' + commit + '&per_page=100')
        candidates = [row for row in response['workflow_runs'] if row['head_branch'] == tag and row['path'] == '.github/workflows/release.yml']
        if len(candidates) == 1:
            run = candidates[0]['id']
            break
        cancelled.wait(5)
    if run is None:
        raise RuntimeError('Release tag was pushed; inspect that exact tag rather than pushing/dispatching again.')
    result = client.wait(run, commit, timeout=13600, cancelled=cancelled,
                         progress=lambda value: print(json.dumps(value), flush=True))
    if result.get('status') == 'cancelled':
        return 1
    release = client.request('GET', client.base + '/releases/tags/' + tag)
    assets = [a for a in release['assets'] if a['name'] == 'release.zip' and a.get('digest', '').startswith('sha256:')]
    if (release['draft'] or len(assets) != 1 or release['prerelease'] != (channel in ('alpha', 'beta'))
            or client.resolve_ref(tag) != commit):
        raise RuntimeError('Workflow finished without a verified published ZIP/digest.')
    from Scripts.release_verification import verify_asset
    dependency = git(root, 'ls-tree', commit, 'Python/commonUtils').split()[2]
    verified = verify_asset(assets[0], commit, dependency, cancelled, tag=tag)
    print(json.dumps(dict(release=release['html_url'], tag=tag, commit=commit, verified=verified)), flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        from build_manager.redaction import Redactor
        print(Redactor()(str(error)), file=sys.stderr)
        raise SystemExit(1)
