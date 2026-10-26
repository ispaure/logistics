"""Human-facing setting metadata; values and persistence belong to manager_settings."""
SECTIONS = {
    'tools': 'Tools and runtimes', 'ios': 'iOS simulators', 'android': 'Android emulator',
    'vm': 'Virtual machines', 'testflight': 'TestFlight', 'firebase': 'Firebase',
    'auth': 'Credentials', 'signing': 'Apple signing', 'github': 'GitHub releases',
    'app': 'App version', 'build': 'Build numbers',
}
HELP = {
    'tools.desktop_python': 'Python executable for desktop tests and tools on this computer.',
    'tools.manager_checkout': 'Reviewed local manager checkout for guest setup when its exact project pin is not published yet. Blank explicitly installs the remote pin; local sources and their real commonUtils pin are verified before transfer.',
    'tools.mobile_python': 'Python executable in the mobile build environment on this computer.',
    'tools.xcode': 'Xcode Developer directory for this run. Blank uses the selected system Xcode; it does not change that selection.',
    'tools.android_sdk': 'Android SDK directory containing platform tools, emulator and system images.',
    'tools.java': 'Java home used by Android Gradle builds. Blank inherits the environment.',
    'ios.iphone': 'Simulator model selector for the iPhone test backend. Tests use an owned disposable simulator.',
    'ios.duo': 'Simulator model selector for compact multi-window iOS coverage. Tests use an owned disposable simulator.',
    'ios.ipad': 'Simulator model selector for iPad coverage, when that run option is enabled.',
    'android.avd': 'Legacy existing AVD selector is unsupported. Leave empty; the manager creates and removes its own emulator.',
    'android.image': 'Installed Android SDK system-image package used to create the disposable test emulator.',
    'android.model': 'Android hardware profile used for the disposable emulator, such as pixel_9.',
    'vm.fedora': 'Dedicated Fedora test machine. The manager fills an empty value from its owned Linux machine; Save remembers the UUID in private project settings. Create or recover it in Setup → Test machines if unavailable.',
    'vm.windows': 'Dedicated Windows test machine. The manager fills an empty value from its owned Windows machine; Save remembers the UUID in private project settings. Create or recover it in Setup → Test machines if unavailable.',
    'vm.fedora_mode': 'Use guest for the dedicated Fedora machine (recommended). container-on-ubuntu is an advanced alternative requiring a separately configured Ubuntu test host with rootless Podman.',
    'vm.fedora_container_host': 'Only for container-on-ubuntu mode: the explicitly authorized Ubuntu test VM name or UUID. Direct Fedora guest testing does not use this field.',
    'vm.windows_prepared_reference': 'Local JSON reference to prepared Windows tools. This is a path, not a tool download or credential.',
    'vm.shared_host': 'Reserved legacy shared-folder field. Isolated backends do not use it.',
    'vm.shared_guest': 'Reserved legacy shared-folder field. Isolated backends do not use it.',
    'vm.shutdown_after_run': 'Shut down the configured test VM after its operation. Enable only for a dedicated VM.',
    'auth.testflight_reference': 'Local App Store Connect authentication JSON file. Its contents are never entered here or synced to GitHub.',
    'auth.key_reference': 'Path to the existing App Store Connect private key. Store only its path here, never paste the key.',
    'auth.github_reference': 'Selected GitHub account reference: an environment variable name or an existing credential-helper label, never a token value.',
    'auth.github_kind': 'Choose the selected account reference mechanism. An explicit missing environment reference never falls back to another account.',
    'auth.reference_status': 'Whether the configured authentication reference file exists. This does not verify server access.',
    'signing.app_profile': 'Existing provisioning profile file for the main Apple app; must match the pinned identity.',
    'signing.inbox_profile': 'Existing provisioning profile file for the Apple inbox extension.',
    'signing.team': 'Pinned Apple developer team from the existing device/signing configuration. Read only.',
    'testflight.app_id': 'App Store Connect application identifier. Identity is guarded and cannot be changed here.',
    'testflight.bundle_id': 'Apple application bundle identifier. Identity is guarded and cannot be changed here.',
    'testflight.enabled': 'Enable the configured external TestFlight distribution step. Upload still requires a reviewed operation.',
    'testflight.external_group': 'Existing external beta tester group to receive this build, for example Friends. This is a group name, not tester addresses.',
    'testflight.locale': 'Locale for the TestFlight testing notes, such as en-US.',
    'testflight.what_to_test': 'Tester-facing notes describing what to test in the uploaded build.',
    'testflight.poll_interval_seconds': 'Seconds between App Store processing checks; allowed range 1–60.',
    'testflight.processing_timeout_seconds': 'Maximum seconds to wait for App Store processing; allowed range 1–3600. Timing out does not undo an upload.',
    'firebase.app_id': 'Firebase Android application identifier from the Firebase project. This identifier is not an API credential.',
    'firebase.bundle_id': 'Android package identity. Guarded to preserve the existing application and its data.',
    'firebase.group': 'Existing Firebase tester group alias that receives the release.',
    'firebase.release_notes': 'Notes for Firebase testers for this distribution.',
    'github.repository': 'GitHub owner/repository that receives releases and workflow requests.',
    'github.token_environment': 'Name of the environment variable containing an optional GitHub token; never the token value.',
    'github.authentication': 'Local GitHub authentication mechanism. Credentials stay with the existing credential provider.',
    'github.workflow': 'Workflow filename to use for hosted validation and release work.',
    'github.credentials': 'Hosted jobs use repository secrets and variables. Local credential files are never copied to the workflow.',
    'app.version': 'Version in tracked pyproject.toml. Use Change tracked app version to intentionally edit source.',
    'build.uniqueness': 'Local allocation prevents duplicate build reservations on this machine; other machines need provider verification.',
    'build.next_ios': 'Preview of the next iOS build number. A number is reserved only when a build starts.',
    'build.next_android': 'Preview of the next Android build number. A number is reserved only when a build starts.',
}


def describe_settings(rows):
    for name, entry in rows.items():
        entry.setdefault('section', SECTIONS.get(name.split('.')[0], 'Capabilities'))
        entry.setdefault('label', name.split('.', 1)[1].replace('_', ' ').capitalize())
        if name in HELP:
            entry['description'] = HELP[name]
        elif entry.get('read_only') and entry.get('description'):
            pass
        else:
            raise ValueError('Setting needs an explicit explanation: '+name)
        if name.endswith('app_id'):
            entry['label'] = 'Application ID'
        elif name.endswith('bundle_id'):
            entry['label'] = 'Bundle / package ID'
        elif name == 'testflight.poll_interval_seconds':
            entry['label'] = 'Processing check interval'
        elif name == 'testflight.processing_timeout_seconds':
            entry['label'] = 'Processing timeout'
        if name in {'testflight.what_to_test','testflight.external_group','firebase.release_notes','firebase.group'}:
            entry['section']='Defaults for new runs'
            entry['description'] += ' This is a saved default; the run screen can override it without changing this profile.'
        if name in ('testflight.what_to_test', 'firebase.release_notes'):
            entry['kind'] = 'multiline'
        if name == 'auth.github_kind':
            entry['choices'] = ('auto','credential-helper','environment-name')
        if name in ('vm.fedora', 'vm.windows'):
            entry['label'] = 'Fedora test machine' if name == 'vm.fedora' else 'Windows test machine'
            if entry.get('origin', '').startswith('Automatic selection unavailable:'):
                entry['description'] += ' ' + entry['origin']
        if name == 'vm.fedora_mode':
            entry['label'] = 'Fedora execution mode'
            entry['choices'] = ('guest', 'container-on-ubuntu')
        if name == 'vm.fedora_container_host':
            entry['label'] = 'Ubuntu host for Fedora container (advanced)'
            entry['visible_when'] = {'vm.fedora_mode': 'container-on-ubuntu'}
        if name == 'vm.fedora':
            entry['visible_when'] = {'vm.fedora_mode': 'guest'}
        if entry.get('kind') == 'int':
            entry.update(minimum=1, maximum=60 if name.endswith('poll_interval_seconds') else 3600, suffix=' s')
    return rows
