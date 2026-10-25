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

from build_manager import Phase, Plan
from mobile_build.deployment import manager_settings
from Scripts.build_snapshots import git, identity, materialize
from Scripts.validation_plans import desktop_checks


class LogisticsProject:
    platforms = ('macos', 'linux', 'windows', 'ios', 'android')
    operations = ('Test', 'Build', 'Prepare TestFlight', 'Prepare Firebase', 'Release')
    description = 'Select source, platform and execution location; inspect the ordered plan before running.'

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.mobile = self.root / 'mobile_build'
        self.interpreter = self.root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        self.runner_directory = self.root
        self.private = self.mobile / '.tools/build-manager'
        self.results_directory = self.root / 'test-results/build-manager'

    def backend_options(self, target):
        return ('Local Parallels VM', 'GitHub') if target in ('linux', 'windows') else ('This Mac', 'GitHub')

    def settings_view(self):
        values, sources = manager_settings.settings(self.mobile)
        rows = {}
        guarded = {'testflight.app_id', 'testflight.bundle_id', 'firebase.bundle_id',
                   'github.token_environment'}
        for name, value in values.items():
            kind = ('bool' if isinstance(value, bool) else
                    'directory' if name in {'tools.xcode', 'tools.android_sdk', 'tools.java', 'vm.shared_host'} else
                    'reference' if name.endswith('reference') or name.startswith('signing.') or name.endswith('_python') else 'text')
            rows[name] = dict(value=value, origin=sources[name], kind=kind, read_only=name in guarded)
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
        return rows

    def save_settings(self, values):
        manager_settings.save(self.mobile, values)

    def set_app_version(self, value):
        manager_settings.set_app_version(self.mobile, value)

    def make_plan(self, operation, target, backend, *, revision='working-tree', pattern='', build_override='', include_ipad=False, release_tag=''):
        setup_started = time.monotonic()
        if operation not in self.operations or target not in self.platforms or backend not in self.backend_options(target):
            raise ValueError('Unsupported operation/platform/backend selection.')
        if pattern and (not pattern.endswith('.py') or '/' in pattern or '\\' in pattern):
            raise ValueError('Use a focused test filename/glob, not a path or command.')
        source = identity(self.root, revision)
        source.update(host=platform.platform(), architecture=platform.machine())
        source['app_version'] = manager_settings.app_version(self.mobile)
        options, _ = manager_settings.settings(self.mobile)
        workspace = self.private / 'workspaces' / target
        if backend == 'GitHub':
            return self.github_plan(operation, target, source, workspace, options, revision, release_tag)
        if operation == 'Release':
            raise ValueError('Choose GitHub for a release; tests do not publish automatically.')
        if target in ('linux', 'windows'):
            return self.local_vm_plan(operation, target, source, workspace, options, pattern)
        if target == 'macos':
            from build_manager.local import inspect_python
            source['toolchain'] = inspect_python(options['tools.desktop_python'], ('Pillow', 'PySide6', 'pyzipper', 'yt-dlp'))
            if source['toolchain']['system'] != 'Darwin':
                raise ValueError('The selected interpreter does not run on macOS; no fallback was selected.')
        snapshot = self.private / 'snapshots' / source['fingerprint']
        materialize(self.root, snapshot, revision)
        env = dict(PYTHONPATH=os.pathsep.join((str(snapshot), str(snapshot / 'Python'))),
                   QT_QPA_PLATFORM='offscreen', PYTHONUNBUFFERED='1')
        python = options['tools.desktop_python']
        if target == 'macos':
            if sys.platform != 'darwin':
                raise ValueError('This Mac backend requires macOS; no fallback was selected.')
            if operation != 'Test':
                raise ValueError('Desktop Build is not implemented by the existing source-package workflow; select Test or GitHub release.')
            commands = [('focused', ['dev.py', 'test', 'desktop', pattern, '--python', python], 600)] if pattern else desktop_checks('Darwin', workspace / 'reports')
            if not pattern:
                commands += [('release-tooling', ['-m', 'unittest', 'discover', '-s', '.github/scripts', '-p', 'test_*.py'], 300)]
            env['LOGISTICS_REQUIRE_LOCALCRYPT_TESTS'] = '1'
            prerequisites = Phase('environment', (python, '-m', 'Scripts.local_desktop'), str(snapshot),
                                  timeout=180, environment=env, kind='setup')
            phases = (prerequisites,) + tuple(Phase(name, (python, *arguments), str(snapshot), timeout=timeout,
                                 environment=env, dependencies=('environment',)) for name, arguments, timeout in commands)
            source['plan_preparation_seconds'] = time.monotonic() - setup_started
            return Plan('Logistics', operation, source, phases, str(workspace), backend=backend)
        return self.mobile_plan(operation, target, source, snapshot, workspace, options, env,
                                pattern, build_override, include_ipad)

    def github_plan(self, operation, target, source, workspace, options, revision, release_tag):
        if revision == 'working-tree' and source['dirty']:
            raise ValueError('GitHub cannot run uncommitted source. Select an explicitly published revision.')
        if operation == 'Release':
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
            command = (str(self.interpreter), '-m', 'Scripts.build_project', 'github', '--platform', target,
                       '--workflow', workflow, '--ref', ref, '--commit', source['logistics_commit'], '--root', str(self.root))
            phases.append(Phase('github-' + name, command, str(self.root), timeout=14400))
        return Plan('Logistics', operation, source, tuple(phases),
                    str(workspace), backend='GitHub', effect='publish')

    def local_vm_plan(self, operation, target, source, workspace, options, pattern):
        if target == 'windows':
            return self.windows_vm_plan(operation, source, workspace, options, pattern)
        if operation != 'Test':
            raise ValueError('This Linux backend accepts Test plans; no Build operation is implied.')
        from build_manager.parallels import Parallels
        client = Parallels()
        selections = []
        for distribution, key in (('ubuntu', 'vm.linux'), ('fedora', 'vm.fedora')):
            if options['vm.linux_scope'] not in ('both', distribution):
                continue
            guest = client.selected(options[key])
            selections.append((distribution, guest))
        if len(selections) == 2 and selections[0][1]['uuid'] == selections[1][1]['uuid']:
            raise ValueError('Select distinct Ubuntu and Fedora guests for the full Linux coverage.')
        snapshot = self.private / 'snapshots' / source['fingerprint']
        materialize(self.root, snapshot, source['selection'])
        phases = []
        for distribution, guest in selections:
            results = workspace / (distribution + '-' + uuid4().hex)
            command = (str(self.interpreter), '-m', 'Scripts.vm_backend', '--vm', guest['uuid'],
                '--snapshot', str(snapshot), '--results', str(results), '--distribution', distribution,
                '--source-identity', json.dumps(source))
            if options['vm.shutdown_after_run']:
                command += ('--shutdown',)
            if pattern:
                command += ('--pattern', pattern)
            phases.append(Phase(distribution, command, str(snapshot), timeout=5400,
                                artifacts=(str(results / 'result.json'),)))
        source['selected_guests'] = [{'distribution': distro, 'name': guest['name'],
                                      'uuid': guest['uuid'], 'initial_state': guest['status']} for distro, guest in selections]
        source['linux_coverage'] = options['vm.linux_scope']
        source['focused_pattern'] = pattern
        return Plan('Logistics', 'Local Linux tests (' + options['vm.linux_scope'] + ')', source, tuple(phases), str(workspace),
                    backend='Local Parallels VM')

    def windows_vm_plan(self, operation, source, workspace, options, pattern):
        if operation != 'Test':
            raise ValueError('Windows guest supports Test plans; no Build operation is implied.')
        from build_manager.parallels import Parallels
        guest = Parallels().selected(options['vm.windows'])
        snapshot = self.private / 'snapshots' / source['fingerprint']
        materialize(self.root, snapshot, source['selection'])
        results = workspace / ('windows-' + uuid4().hex)
        command = (str(self.interpreter), '-m', 'Scripts.windows_backend', '--vm', guest['uuid'],
                   '--snapshot', str(snapshot), '--results', str(results), '--source-identity', json.dumps(source))
        prepared = options['vm.windows_prepared_reference']
        if prepared:
            command += ('--prepared', prepared)
        if pattern:
            command += ('--pattern', pattern)
        if options['vm.shutdown_after_run']:
            command += ('--shutdown',)
        source.update(selected_guest=guest, focused_pattern=pattern)
        return Plan('Logistics', 'Focused Windows contracts' if pattern else 'Complete local Windows tests', source,
                    (Phase('windows', command, str(snapshot), timeout=5400, artifacts=(str(results / 'result.json'),)),),
                    str(workspace), backend='Local Parallels VM')

    def mobile_plan(self, operation, target, source, snapshot, workspace, options, env, pattern, build_override, include_ipad):
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
            for name in ('.venv', '.tools', '.device.json', '.testflight-auth.json', '.android-beta'):
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
            phase = Phase('prepare-verified-artifact', (options['tools.mobile_python'], '-m',
                'mobile_build.deployment.' + module, *arguments), str(snapshot), timeout=14400,
                environment=env, kind='build', artifacts=(str(artifact),))
            return Plan('Logistics', operation, source, (phase,), str(workspace), backend='This Mac', effect='build')
        raise ValueError('Local mobile backend is not installed yet; no hosted fallback or passing result is implied.')

    def verification_plan(self):
        source = identity(self.root)
        command = (str(self.interpreter), '-m', 'Scripts.build_project', 'verify', '--root', str(self.root))
        return Plan('Logistics', 'Read-only connection verification', source,
                    (Phase('verify-settings', command, str(self.root), timeout=120, kind='inspect'),),
                    str(self.private / 'verification'), effect='inspect')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('verify', 'github', 'release'))
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--platform', choices=LogisticsProject.platforms)
    parser.add_argument('--ref')
    parser.add_argument('--commit')
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
        print(json.dumps(dict(run_id=run, repository=values['github.repository'], status='queued')), flush=True)
        result = client.wait(run, args.commit, timeout=13800, cancelled=cancelled,
                             progress=lambda value: print(json.dumps(value), flush=True))
        return int(result.get('status') != 'completed')
    return release_source(args.root, client, args.tag, args.commit, cancelled)


def github_client(values, root):
    from build_manager.github import GitHub
    token = os.environ.get(values['github.token_environment'])
    if not token and values['github.authentication'] == 'existing git credential helper':
        result = subprocess.run(['git', 'credential', 'fill'], cwd=root,
            input='protocol=https\nhost=github.com\n\n', text=True, capture_output=True,
            timeout=30, env=dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='Never'))
        if result.returncode == 0:
            saved = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
            token = saved.get('password')
    return GitHub(values['github.repository'], token)


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
    print(json.dumps(dict(release=release['html_url'], tag=tag, commit=commit, digest=assets[0]['digest'])), flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        from build_manager.redaction import Redactor
        print(Redactor()(str(error)), file=sys.stderr)
        raise SystemExit(1)
