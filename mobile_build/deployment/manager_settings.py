"""Logistics settings adapter shared by the manager and distribution CLIs."""
import json
import os
from pathlib import Path
import re
import subprocess
import tomllib

from build_manager.profiles import effective, load_profile, save_profile


def profile_path(root):
    return Path(os.environ.get('LOGISTICS_MANAGER_PROFILE') or Path(root) / '.tools/build-manager/profile.json')


def loaded_profile(root):
    path = profile_path(root)
    legacy = os.environ.get('LOGISTICS_MANAGER_LEGACY_PROFILE')
    if not path.exists() and legacy:
        return load_profile(legacy)
    return load_profile(path)


def defaults(root):
    root = Path(root)
    testflight = json.loads((root / 'testflight-distribution.json').read_text())
    firebase = json.loads((root / 'firebase-distribution.json').read_text())
    auth_path = root / '.testflight-auth.json'
    auth = json.loads(auth_path.read_text()) if auth_path.exists() else {}
    values = {'testflight.' + k: v for k, v in testflight.items()}
    values.update({'firebase.' + k: v for k, v in firebase.items()})
    values.update({
        'tools.desktop_python': str(root.parent / '.venv/bin/python'),
        'tools.mobile_python': str(root / '.venv/bin/python'),
        'tools.xcode': '', 'tools.android_sdk': '', 'tools.java': '',
        'tools.manager_checkout': '',
        'ios.iphone': '', 'ios.duo': '', 'ios.ipad': '', 'android.avd': '',
        'android.image': 'system-images;android-36;google_apis;arm64-v8a', 'android.model': 'pixel_9',
        'vm.fedora': '', 'vm.windows': '',
        'vm.fedora_mode': 'guest', 'vm.fedora_container_host': '',
        'vm.windows_prepared_reference': str(root / '.tools/build-manager/windows-prepared.json'),
        'vm.shared_host': '', 'vm.shared_guest': '', 'vm.shutdown_after_run': False,
        'auth.testflight_reference': str(root / '.testflight-auth.json'),
        'auth.key_reference': auth.get('key_path', ''),
        'auth.github_reference': '', 'auth.github_kind': 'auto',
        'signing.app_profile': '', 'signing.inbox_profile': '',
        'signing.widget_profile': '', 'signing.widget_actions_profile': '',
        'signing.watch_profile': '', 'signing.watch_widget_profile': '',
        'github.repository': 'ispaure/logistics', 'github.token_environment': 'GH_TOKEN',
        'github.authentication': 'existing git credential helper',
        'github.workflow': 'release.yml',
        'firebase.release_notes': '',
    })
    from logistics_build.test_environments import load
    values.update({'testing.' + key: value for key, value in load(root.parent).items()})
    return values


VARIABLES = {
    'testflight.external_group': 'LOGISTICS_TESTFLIGHT_GROUP',
    'firebase.group': 'LOGISTICS_FIREBASE_GROUP',
    'tools.android_sdk': 'ANDROID_HOME', 'tools.java': 'JAVA_HOME',
    'tools.xcode': 'DEVELOPER_DIR',
}


def current_settings(values):
    """Discard retired Ubuntu selectors from saved profiles and captured overrides."""
    return {key: value for key, value in values.items() if key not in {'vm.linux', 'vm.linux_scope'} and not key.startswith('testing.')}


def settings(root, *, overrides=None):
    configured = defaults(root)
    from build_manager.settings import Field, resolve
    account = json.loads(os.environ.get('LOGISTICS_MANAGER_ACCOUNT_DEFAULTS', '{}'))
    schema = {key: Field(value, account=key.startswith('auth.'),
                        machine=key.startswith(('tools.', 'vm.', 'ios.', 'android.')),
                        guarded=key in {'testflight.app_id', 'testflight.bundle_id', 'firebase.bundle_id'},
                        variable=VARIABLES.get(key)) for key, value in configured.items()}
    values, sources = resolve(schema, account=account, profile=current_settings(loaded_profile(root)),
                              environment=os.environ, overrides=current_settings(overrides or {}))
    validate(values, configured)
    for key in configured:
        if key.startswith('testing.'):
            sources[key] = 'tracked test-environments.json; shared with GitHub'
    from logistics_build.test_environments import load, android_image
    test_environment = load(Path(root).parent)
    values['android.image'] = android_image(test_environment)
    values['android.model'] = test_environment['android_model']
    sources['android.image'] = sources['android.model'] = 'derived from shared test environment settings'
    # Discover only checkout-owned dedicated guests, never adopt a named personal VM.
    # Frozen run profiles already contain resolved UUIDs and must remain authoritative.
    if os.environ.get('LOGISTICS_MANAGER_CHECKOUT'):
        from build_manager.vm import dedicated_guest
        for key, kind in (('vm.fedora', 'linux'), ('vm.windows', 'windows')):
            if values[key] or (kind == 'linux' and values['vm.fedora_mode'] != 'guest'):
                continue
            try:
                selector = dedicated_guest(kind, os.environ['LOGISTICS_MANAGER_CHECKOUT'])
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                from build_manager.redaction import Redactor
                sources[key] = 'Automatic selection unavailable: ' + Redactor()(str(error))
                continue
            if selector:
                values[key], sources[key] = selector, 'Detected dedicated test machine; Save keeps its UUID in your private project settings'
    return values, sources


def validate(values, configured):
    if values['auth.github_kind'] not in {'auto','environment-name','credential-helper'}:
        raise ValueError('Unsupported GitHub account reference kind.')
    if values['auth.github_kind']=='environment-name' and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',values['auth.github_reference']):
        raise ValueError('GitHub account references contain environment names, never tokens.')
    for name in ('testflight.poll_interval_seconds', 'testflight.processing_timeout_seconds'):
        try:
            values[name] = int(values[name])
        except (TypeError, ValueError):
            raise ValueError(name + ' must be an integer.') from None
    for name in ('testflight.enabled', 'vm.shutdown_after_run'):
        if not isinstance(values[name], bool):
            raise ValueError(name + ' must be a boolean.')
    for name in ('testflight.app_id', 'testflight.bundle_id', 'firebase.bundle_id'):
        if values[name] != configured[name]:
            raise ValueError('App identity is guarded; configure it through the existing identity workflow: ' + name)
    if not 1 <= values['testflight.poll_interval_seconds'] <= 60:
        raise ValueError('TestFlight poll interval must be 1–60 seconds.')
    if not 1 <= values['testflight.processing_timeout_seconds'] <= 3600:
        raise ValueError('TestFlight processing limit must be 1–3600 seconds.')
    if not re.fullmatch(r'1:\d+:android:[a-f0-9]+', values['firebase.app_id']):
        raise ValueError('Invalid Firebase application identifier.')
    for name in ('testflight.external_group', 'firebase.group', 'testflight.what_to_test'):
        if not str(values[name]).strip():
            raise ValueError(name + ' cannot be empty.')


def distribution(root, provider, original):
    # Existing tests/consumers may supply only the provider's settings file.
    # No profile means the established defaults remain the sole source.
    root = Path(root)
    if not loaded_profile(root) and not any(name in os.environ for key, name in VARIABLES.items()
                                                  if key.startswith(provider + '.')):
        return original
    # The caller's loaded provider file is authoritative. A profile containing
    # only VM/tool settings must not replace it with another file's defaults.
    configured = {provider + '.' + key: value for key, value in original.items()}
    profile = {key: value for key, value in loaded_profile(root).items() if key in configured}
    variables = {key: name for key, name in VARIABLES.items() if key in configured}
    values, _ = effective(configured, profile, os.environ, variables=variables)
    guarded = ['bundle_id'] + (['app_id'] if provider == 'testflight' else [])
    for key in guarded:
        name = provider + '.' + key
        if key in original and values[name] != original[key]:
            raise ValueError('App identity is guarded: ' + name)
    return {key: values[provider + '.' + key] for key in original}


def save(root, changes):
    from logistics_build.test_environments import load, save as save_environments, validate as validate_environments
    environment_changes = {key.removeprefix('testing.'): value for key, value in changes.items() if key.startswith('testing.')}
    validate_environments(dict(load(Path(root).parent), **environment_changes))
    changes = {key: value for key, value in changes.items() if not key.startswith('testing.')}
    base = defaults(root)
    current = loaded_profile(root)
    incoming = current_settings(dict(current, **changes))
    values, _ = effective(base, incoming)
    validate(values, base)
    for key in ('testflight.poll_interval_seconds', 'testflight.processing_timeout_seconds'):
        incoming[key] = int(values[key])
    if environment_changes:
        save_environments(Path(root).parent, environment_changes)
    save_profile(profile_path(root), incoming, allowed=base)


def app_version(root, *, revision=None, check_project=True):
    if revision is None:
        text = (Path(root) / 'pyproject.toml').read_text()
    else:
        text = subprocess.check_output(['git', '-C', str(Path(root).parent), 'show',
            revision + ':mobile_build/pyproject.toml'], text=True, timeout=30)
    version = tomllib.loads(text)['tool']['briefcase']['version']
    desktop = Path(root).parent / 'Python/pyproject.toml'
    if check_project and desktop.is_file():
        desktop_text = (desktop.read_text() if revision is None else subprocess.check_output(
            ['git', '-C', str(Path(root).parent), 'show', revision + ':Python/pyproject.toml'],
            text=True, timeout=30))
        if tomllib.loads(desktop_text)['project']['version'] != version:
            raise ValueError('Desktop and mobile app versions differ. Use build-manager set-version before planning.')
    return version


def record_prepared_artifact(record):
    destination = os.environ.get('LOGISTICS_MANAGER_ARTIFACT_REPORT')
    if not destination:
        return
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(record, indent=2) + '\n')
    temporary.replace(path)


def authentication_references(root):
    account = json.loads(os.environ.get('LOGISTICS_MANAGER_ACCOUNT_DEFAULTS', '{}'))
    if set(account) - {'auth.testflight_reference', 'auth.key_reference', 'auth.github_reference', 'auth.github_kind'}:
        raise ValueError('Shared accounts may supply protected auth references only.')
    return dict(account, **{key: value for key, value in loaded_profile(root).items() if key.startswith('auth.')})
