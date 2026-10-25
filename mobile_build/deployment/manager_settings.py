"""Logistics settings adapter shared by the manager and distribution CLIs."""
import json
import os
from pathlib import Path
import re
import tomllib

from build_manager.profiles import effective, load_profile, save_profile


def profile_path(root):
    return Path(os.environ.get('LOGISTICS_MANAGER_PROFILE') or Path(root) / '.tools/build-manager/profile.json')


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
        'ios.iphone': '', 'ios.duo': '', 'ios.ipad': '', 'android.avd': '',
        'android.image': 'system-images;android-36;google_apis;arm64-v8a', 'android.model': 'pixel_9',
        'vm.linux': '', 'vm.fedora': '', 'vm.windows': '',
        'vm.linux_scope': 'both', 'vm.fedora_mode': 'guest', 'vm.fedora_container_host': '',
        'vm.windows_prepared_reference': str(root / '.tools/build-manager/windows-prepared.json'),
        'vm.shared_host': '', 'vm.shared_guest': '', 'vm.shutdown_after_run': False,
        'auth.testflight_reference': str(root / '.testflight-auth.json'),
        'auth.key_reference': auth.get('key_path', ''),
        'signing.app_profile': '', 'signing.inbox_profile': '',
        'github.repository': 'ispaure/logistics', 'github.token_environment': 'GH_TOKEN',
        'github.authentication': 'existing git credential helper',
        'github.workflow': 'release.yml',
        'firebase.release_notes': '',
    })
    return values


VARIABLES = {
    'testflight.external_group': 'LOGISTICS_TESTFLIGHT_GROUP',
    'firebase.group': 'LOGISTICS_FIREBASE_GROUP',
    'tools.android_sdk': 'ANDROID_HOME', 'tools.java': 'JAVA_HOME',
    'tools.xcode': 'DEVELOPER_DIR',
}


def settings(root, *, overrides=None):
    configured = defaults(root)
    values, sources = effective(configured, load_profile(profile_path(root)), os.environ,
                                overrides, variables=VARIABLES)
    validate(values, configured)
    return values, sources


def validate(values, configured):
    if values['vm.linux_scope'] not in ('both', 'ubuntu', 'fedora'):
        raise ValueError('Linux coverage must be both, ubuntu or fedora; partial runs remain labelled partial.')
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
    if not profile_path(root).exists() and not any(name in os.environ for key, name in VARIABLES.items()
                                                  if key.startswith(provider + '.')):
        return original
    # The caller's loaded provider file is authoritative. A profile containing
    # only VM/tool settings must not replace it with another file's defaults.
    configured = {provider + '.' + key: value for key, value in original.items()}
    profile = {key: value for key, value in load_profile(profile_path(root)).items() if key in configured}
    variables = {key: name for key, name in VARIABLES.items() if key in configured}
    values, _ = effective(configured, profile, os.environ, variables=variables)
    guarded = ['bundle_id'] + (['app_id'] if provider == 'testflight' else [])
    for key in guarded:
        name = provider + '.' + key
        if key in original and values[name] != original[key]:
            raise ValueError('App identity is guarded: ' + name)
    return {key: values[provider + '.' + key] for key in original}


def save(root, changes):
    base = defaults(root)
    current = load_profile(profile_path(root))
    incoming = dict(current, **changes)
    values, _ = effective(base, incoming)
    validate(values, base)
    for key in ('testflight.poll_interval_seconds', 'testflight.processing_timeout_seconds'):
        incoming[key] = int(values[key])
    save_profile(profile_path(root), incoming, allowed=base)


def app_version(root):
    return tomllib.loads((Path(root) / 'pyproject.toml').read_text())['tool']['briefcase']['version']


def set_app_version(root, version):
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Use a three-component numeric app version.')
    path = Path(root) / 'pyproject.toml'
    text = path.read_text()
    changed, count = re.subn(r'(?m)^version = "[^"]+"$', 'version = "' + version + '"', text)
    if count != 1:
        raise ValueError('Cannot uniquely identify the tracked app version.')
    path.write_text(changed)


def record_prepared_artifact(record):
    destination = os.environ.get('LOGISTICS_MANAGER_ARTIFACT_REPORT')
    if not destination:
        return
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(record, indent=2) + '\n')
    temporary.replace(path)
