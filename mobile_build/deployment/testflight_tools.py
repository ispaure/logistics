"""Prepare isolated, identity-checked TestFlight archives and explicit uploads."""
import argparse
from fnmatch import fnmatchcase
from hashlib import sha256
from commonUtils.runtime.streams import file_sha256, iter_chunks
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

from .. import cloud_build
from .device_tools import BUNDLE, CONFIG, EXTENSION_SUFFIXES, normal_launcher, signing_settings
from ..select_ios_sdk import choose, installed
from ..tools import stage
from .testflight_external import prepare as prepare_external, distribute as distribute_external
from .testflight_external import credentials as external_credentials, AUTH as EXTERNAL_AUTH
from ..build_support.privacy_build import verify_app as verify_privacy

ROOT = Path(__file__).resolve().parents[1]


def release_identity(team=None, expected=None):
    saved = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    baseline = saved.get('signing_identity', {})
    team = team or saved.get('team_id')
    expected = expected or baseline.get('application_identifier')
    if not team or not re.fullmatch(r'[A-Z0-9]{10}', team):
        raise ValueError('Supply the approved, existing --team ID (or configure local device deployment first).')
    if not expected or not re.fullmatch(r'[A-Z0-9]{10}\.' + re.escape(BUNDLE), expected):
        raise ValueError('Supply --expected-app-identifier with the existing application identifier, including its prefix.')
    if (saved and (saved.get('bundle_id') != BUNDLE or saved.get('team_id') != team)
            or baseline and baseline.get('application_identifier') != expected):
        raise ValueError('Release identity differs from the installed app baseline. Resolve the team mapping; do not change the bundle ID or uninstall.')
    return dict(bundle_id=BUNDLE, team_id=team, application_identifier=expected,
                keychain_access_groups=baseline.get('keychain_access_groups', []))


def build_number(value):
    if not re.fullmatch(r'[1-9][0-9]{0,8}', value):
        raise ValueError('Use a positive build number with at most nine digits; increase it for each upload.')
    return value


def keychain_groups_match(actual, identity):
    # An omitted group uses the application identifier as the default group;
    # distribution signing may make that same default explicit.
    default = [identity['application_identifier']]
    return sorted(actual or default) == sorted(identity['keychain_access_groups'] or default)


def export_options(team, profile=None, *, upload=False, inbox_profile=None, widget_profile=None, widget_actions_profile=None, watch_profile=None, watch_widget_profile=None):
    extensions = {'.inbox': inbox_profile, '.widgets': widget_profile, '.widget-actions': widget_actions_profile, '.watchkitapp': watch_profile, '.watchkitapp.widgets': watch_widget_profile}
    if any(extensions.values()) and not profile:
        raise ValueError('Extension profiles require the containing app profile too.')
    options = dict(method='app-store-connect', destination='upload' if upload else 'export',
                   teamID=team, signingStyle='manual' if profile else 'automatic',
                   manageAppVersionAndBuildNumber=False, uploadSymbols=True)
    if profile:
        options.update(signingCertificate='Apple Distribution', provisioningProfiles={BUNDLE: profile['UUID']})
        for suffix, extension_profile in extensions.items():
            if extension_profile:
                options['provisioningProfiles'][BUNDLE + suffix] = extension_profile['UUID']
    return options


def validate_profile(profile, identity):
    entitlements = profile.get('Entitlements', {})
    # Profiles authorize groups (often PREFIX.*); the signed app must still
    # have exactly the baseline's effective groups, checked by inspect_app.
    required_groups = identity['keychain_access_groups'] or [identity['application_identifier']]
    allowed_groups = entitlements.get('keychain-access-groups', [identity['application_identifier']])
    groups_authorized = all(any(fnmatchcase(group, allowed) for allowed in allowed_groups)
                            for group in required_groups)
    if (profile.get('TeamIdentifier') != [identity['team_id']]
            or entitlements.get('application-identifier') != identity['application_identifier']
            or entitlements.get('get-task-allow') is not False
            or entitlements.get('beta-reports-active') is not True
            or not groups_authorized
            or profile.get('ProvisionedDevices') or profile.get('ProvisionsAllDevices')):
        raise ValueError('Use an App Store distribution profile for the exact existing Logistics identity, not a development/ad-hoc profile.')
    from datetime import datetime, timezone
    if profile['ExpirationDate'].replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
        raise ValueError('Distribution profile has expired.')


def run(args, directory, env, log):
    log.parent.mkdir(parents=True, exist_ok=True)
    print('Running ' + args[0] + '; log: ' + str(log), flush=True)
    with log.open('w') as stream:
        result = subprocess.run(args, cwd=directory, env=env, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed; see {log}\n' + '\n'.join(log.read_text(errors='replace').splitlines()[-15:]))


def inspect_app(app, identity, number, *, signed=True, distribution=False):
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    if (info.get('CFBundleIdentifier') != BUNDLE or info.get('MainModule') != 'logisticsmobile'
            or info.get('CFBundleVersion') != number):
        raise ValueError('Archive identity, build number or normal launcher differs.')
    if (app / 'app/tests').exists():
        raise ValueError('Test entry point found in release app.')
    verify_privacy(app)
    if signed:
        entitlements = plistlib.loads(subprocess.check_output(
            ['codesign', '-d', '--entitlements', ':-', str(app)], stderr=subprocess.DEVNULL))
        if (entitlements.get('application-identifier') != identity['application_identifier']
                or entitlements.get('com.apple.developer.team-identifier') != identity['team_id']
                or not keychain_groups_match(entitlements.get('keychain-access-groups', []), identity)):
            raise ValueError('Signed application identifier, team or Keychain groups differ from the baseline.')
        if distribution and entitlements.get('get-task-allow') is not False:
            raise ValueError('Exported app still permits debugging.')
        profile = plistlib.loads(subprocess.check_output(['security', 'cms', '-D', '-i', str(app / 'embedded.mobileprovision')]))
        if distribution:
            validate_profile(profile, identity)
        subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
    return dict(bundle_id=BUNDLE, version=info['CFBundleShortVersionString'], build_number=number,
                signed=signed, distribution=distribution)


def auth_args():
    values = [os.environ.get(name) for name in ('ASC_KEY_PATH', 'ASC_KEY_ID', 'ASC_ISSUER_ID')]
    if any(values) and not all(values):
        raise ValueError('Set all of ASC_KEY_PATH, ASC_KEY_ID and ASC_ISSUER_ID, or use your signed-in Xcode account.')
    if not all(values):
        from . import testflight_external
        reference = testflight_external.auth_reference() if EXTERNAL_AUTH == testflight_external.AUTH else EXTERNAL_AUTH
        if not reference.exists():
            return []
        saved = external_credentials()
        values = [saved['key_path'], saved['key_id'], saved['issuer_id']]
    if not Path(values[0]).is_file():
        raise ValueError('App Store Connect API key file is missing.')
    return ['-authenticationKeyPath', values[0], '-authenticationKeyID', values[1], '-authenticationKeyIssuerID', values[2]]


def archive_fingerprint(app):
    digest = sha256()
    for path in sorted(app.rglob('*')):
        if path.is_file():
            digest.update(path.relative_to(app).as_posix().encode() + b'\0')
            with path.open('rb') as stream:
                for chunk in iter_chunks(stream):
                    digest.update(chunk)
    return digest.hexdigest()


def archive_release(args, workspace, identity, env):
    if workspace.exists():
        raise ValueError('Release workspace already exists; select a new build number. Existing archives are preserved.')
    workspace.mkdir(parents=True)
    shutil.copyfile(ROOT / 'pyproject.toml', workspace / 'pyproject.toml')
    try:
        manifest = stage(ROOT.parent, workspace / 'payload', allow_dirty=True)
        cloud_build.licenses(workspace / 'payload/mobile/native-licenses')
        run([sys.executable, '-m', 'briefcase', 'create', 'iOS', '--no-input'], workspace, env, workspace / 'logs/create.log')
        project = workspace / 'build/logisticsmobile/ios/xcode'
        cloud_build.run('go', 'test', './...', env=env)
        cloud_build.ios(project)
        pbx = project / 'Logistics Mobile.xcodeproj/project.pbxproj'
        data = signing_settings(json.loads(subprocess.check_output(['plutil', '-convert', 'json', '-o', '-', str(pbx)])), identity['team_id'])
        profile = None
        extension_profiles = {}
        if args.profile:
            profile = plistlib.loads(subprocess.check_output(['security', 'cms', '-D', '-i', str(args.profile.resolve())]))
            validate_profile(profile, identity)
            for suffix, argument in (('.inbox', 'inbox_profile'), ('.widgets', 'widget_profile'),
                                     ('.widget-actions', 'widget_actions_profile'), ('.watchkitapp', 'watch_profile'),
                                     ('.watchkitapp.widgets', 'watch_widget_profile')):
                path = getattr(args, argument, None)
                if not any(obj.get('buildSettings', {}).get('PRODUCT_BUNDLE_IDENTIFIER') == BUNDLE + suffix
                           for obj in data['objects'].values()):
                    continue
                if not path:
                    raise ValueError('Manual signing requires --' + argument.replace('_', '-') + ' for the extension.')
                extension_profile = plistlib.loads(subprocess.check_output(['security', 'cms', '-D', '-i', str(path.resolve())]))
                validate_profile(extension_profile, dict(identity, bundle_id=BUNDLE + suffix,
                    application_identifier=identity['application_identifier'] + suffix, keychain_access_groups=[]))
                extension_profiles[suffix] = extension_profile
            from ..build_support.incoming_build import GROUP
            if any(GROUP not in p.get('Entitlements', {}).get('com.apple.security.application-groups', [])
                   for p in (profile, *extension_profiles.values())):
                raise ValueError('App and all extension profiles must authorize the Logistics App Group.')
            for obj in data['objects'].values():
                settings = obj.get('buildSettings', {})
                selected_profile = {BUNDLE: profile, **{BUNDLE + suffix: p for suffix, p in extension_profiles.items()}}.get(settings.get('PRODUCT_BUNDLE_IDENTIFIER'))
                if selected_profile:
                    settings.update(CODE_SIGN_STYLE='Manual', CODE_SIGN_IDENTITY='Apple Distribution',
                                    PROVISIONING_PROFILE_SPECIFIER=selected_profile['UUID'])
        for obj in data['objects'].values():
            settings = obj.get('buildSettings', {})
            if settings.get('PRODUCT_BUNDLE_IDENTIFIER') in {BUNDLE + suffix for suffix in EXTENSION_SUFFIXES}:
                settings['CURRENT_PROJECT_VERSION'] = args.build_number
        # Extension plists use literal versions, so update them alongside build settings.
        for folder in ('IncomingShare', 'LogisticsWidget', 'LogisticsWidgetActions', 'LogisticsWatch', 'LogisticsWatchWidget'):
            extension_info = project / folder / 'Info.plist'
            if not extension_info.exists():
                continue
            extension_metadata = plistlib.loads(extension_info.read_bytes())
            extension_metadata['CFBundleVersion'] = args.build_number
            extension_info.write_bytes(plistlib.dumps(extension_metadata))
        pbx.write_bytes(plistlib.dumps(data, sort_keys=False))
        info = project / 'LogisticsMobile/LogisticsMobile-Info.plist'
        metadata = normal_launcher(plistlib.loads(info.read_bytes()))
        metadata['CFBundleVersion'] = args.build_number
        info.write_bytes(plistlib.dumps(metadata))
        command = ['xcodebuild', '-project', str(pbx.parent), '-scheme', 'Logistics Mobile',
                   '-configuration', 'Release', '-sdk', 'iphoneos', '-destination', 'generic/platform=iOS',
                   '-derivedDataPath', str(workspace / 'derived'), '-archivePath', str(workspace / 'Logistics.xcarchive')]
        if args.unsigned_check:
            command += ['CODE_SIGNING_ALLOWED=NO', 'EXPANDED_CODE_SIGN_IDENTITY=-']
        elif not profile:
            command += ['-allowProvisioningUpdates', *auth_args()]
        command += ['archive']
        run(command, workspace, env, workspace / 'logs/archive.log')
        report = inspect_app(workspace / 'Logistics.xcarchive/Products/Applications/Logistics Mobile.app', identity,
                             args.build_number, signed=not args.unsigned_check)
        record = dict(identity=identity, build=report, source=manifest, profile_uuid=profile['UUID'] if profile else None,
                      inbox_profile_uuid=extension_profiles.get('.inbox', {}).get('UUID'),
                      extension_profile_uuids={suffix: p['UUID'] for suffix, p in extension_profiles.items()})
        (workspace / 'release.json').write_text(json.dumps(record, indent=2) + '\n')
        (workspace / 'ExportOptions.plist').write_bytes(plistlib.dumps(export_options(identity['team_id'], profile,
            inbox_profile=extension_profiles.get('.inbox'), widget_profile=extension_profiles.get('.widgets'),
            widget_actions_profile=extension_profiles.get('.widget-actions'),
            watch_profile=extension_profiles.get('.watchkitapp'), watch_widget_profile=extension_profiles.get('.watchkitapp.widgets'))))
        print('Archive prepared: ' + str(workspace))
    except Exception:
        print('Incomplete workspace and diagnostics retained: ' + str(workspace), file=sys.stderr)
        raise


def export_release(workspace, env, *, upload=False):
    external = None
    record = json.loads((workspace / 'release.json').read_text())
    if not record['build']['signed']:
        raise ValueError('Unsigned archives cannot be exported or uploaded. Archive with approved signing first.')
    identity = release_identity(record['identity']['team_id'], record['identity']['application_identifier'])
    if identity != record['identity']:
        raise ValueError('Saved release identity differs from the current baseline.')
    archived_app = workspace / 'Logistics.xcarchive/Products/Applications/Logistics Mobile.app'
    inspect_app(archived_app, identity, record['build']['build_number'])
    if upload:
        if not (workspace / 'export-verified.json').exists():
            raise ValueError('Export and verify the distribution IPA before uploading.')
        verified = json.loads((workspace / 'export-verified.json').read_text())
        ipas = list((workspace / 'export').glob('*.ipa'))
        if (verified.get('archive_sha256') != archive_fingerprint(archived_app)
                or len(ipas) != 1 or verified.get('ipa_sha256') != file_sha256(ipas[0])):
            raise ValueError('Reviewed archive/IPA has changed. Export and verify again before uploading.')
        if not os.environ.get('TESTFLIGHT_UPLOAD') == '1':
            raise ValueError('Uploading is explicit: set TESTFLIGHT_UPLOAD=1 and run upload after reviewing the exported build.')
        external = prepare_external()
    profile = {'UUID': record['profile_uuid']} if record['profile_uuid'] else None
    extensions = dict(record.get('extension_profile_uuids', {}))
    if record.get('inbox_profile_uuid'):
        extensions.setdefault('.inbox', record['inbox_profile_uuid'])
    def extension_profile(suffix):
        return {'UUID': extensions[suffix]} if extensions.get(suffix) else None
    options = export_options(identity['team_id'], profile, upload=upload,
        inbox_profile=extension_profile('.inbox'), widget_profile=extension_profile('.widgets'),
        widget_actions_profile=extension_profile('.widget-actions'),
        watch_profile=extension_profile('.watchkitapp'), watch_widget_profile=extension_profile('.watchkitapp.widgets'))
    destination = workspace / ('UploadOptions.plist' if upload else 'ExportOptions.plist')
    destination.write_bytes(plistlib.dumps(options))
    run(['xcodebuild', '-exportArchive', '-archivePath', str(workspace / 'Logistics.xcarchive'),
         '-exportOptionsPlist', str(destination), '-exportPath', str(workspace / ('upload' if upload else 'export')),
         '-allowProvisioningUpdates', *auth_args()], workspace, env, workspace / ('logs/upload.log' if upload else 'logs/export.log'))
    if upload:
        (workspace / 'upload-result.json').write_text(json.dumps(dict(status='uploaded', build=record['build']), indent=2) + '\n')
        if external is not None:
            distribute_external(workspace, external)
    if not upload:
        ipas = list((workspace / 'export').glob('*.ipa'))
        if len(ipas) != 1:
            raise ValueError('Expected exactly one exported IPA.')
        with tempfile.TemporaryDirectory(prefix='logistics-ipa-') as temporary:
            # ditto preserves executable modes and framework symlinks for
            # recursive signature validation of the exported Apple artifact.
            subprocess.run(['ditto', '-x', '-k', str(ipas[0]), temporary], check=True)
            apps = list((Path(temporary) / 'Payload').glob('*.app'))
            if len(apps) != 1:
                raise ValueError('Unexpected IPA layout.')
            report = inspect_app(apps[0], identity, record['build']['build_number'], distribution=True)
        report.update(archive_sha256=archive_fingerprint(archived_app), ipa_sha256=file_sha256(ipas[0]))
        (workspace / 'export-verified.json').write_text(json.dumps(report, indent=2) + '\n')
        print('Verified App Store distribution IPA: ' + str(ipas[0]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('plan', 'archive', 'export', 'upload', 'distribute'))
    parser.add_argument('--build-number', required=True, type=build_number)
    parser.add_argument('--workspace', type=Path, help='Existing uploaded build workspace; distribute only, never uploads.')
    parser.add_argument('--team')
    parser.add_argument('--expected-app-identifier')
    parser.add_argument('--profile', type=Path, help='Installed App Store profile for manual CI signing')
    parser.add_argument('--inbox-profile', type=Path, help='Matching App Store profile for the Inbox extension')
    parser.add_argument('--widget-profile', type=Path, help='Matching App Store profile for the widget extension')
    parser.add_argument('--widget-actions-profile', type=Path, help='Matching App Store profile for the widget actions extension')
    parser.add_argument('--watch-profile', type=Path, help='Matching App Store profile for the Watch companion')
    parser.add_argument('--watch-widget-profile', type=Path, help='Matching App Store profile for the Watch widget')
    parser.add_argument('--unsigned-check', action='store_true', help='Local archive packaging check only; cannot export/upload')
    args = parser.parse_args()
    if any((args.inbox_profile, args.widget_profile, args.widget_actions_profile, args.watch_profile, args.watch_widget_profile)) and not args.profile:
        parser.error('Extension profiles require --profile for the containing app.')
    if args.unsigned_check and args.command not in ('plan', 'archive'):
        parser.error('--unsigned-check applies only to a local archive check.')
    if args.workspace is not None and args.command != 'distribute':
        parser.error('--workspace applies only to distribution of an existing upload.')
    identity = release_identity(args.team, args.expected_app_identifier)
    config = tomllib.loads((ROOT / 'pyproject.toml').read_text())['tool']['briefcase']
    if config['bundle'] + '.logisticsmobile' != BUNDLE:
        raise ValueError('Briefcase bundle identity has changed.')
    workspace = args.workspace.expanduser().resolve() if args.workspace is not None else ROOT / 'build/testflight' / args.build_number
    if args.command == 'distribute':
        record = json.loads((workspace / 'release.json').read_text())
        uploaded = json.loads((workspace / 'upload-result.json').read_text())
        if (record['identity'] != identity or record['build']['build_number'] != args.build_number
                or uploaded.get('status') != 'uploaded' or uploaded.get('build') != record['build']):
            raise ValueError('Existing uploaded workspace identity/build differs from the selected release.')
    from contextlib import nullcontext
    from build_manager.locking import workspace_lock
    from build_manager.retention import lease
    from logistics_build.build_retention import clean_builds
    # Archive creation must own the retention lock before its directory exists.
    # lease() creates that directory, which archive_release correctly rejects.
    protection = (nullcontext() if args.command == 'plan' else
                  workspace_lock(workspace.parent / ('.' + workspace.name + '.retention.lock'))
                  if args.command == 'archive' else lease(workspace))
    with protection:
        if args.command != 'plan':
            clean_builds(ROOT)
        if args.command == 'distribute':
            distribute_external(workspace)
            return
        if args.command == 'plan':
            print(json.dumps(dict(identity=identity, version=config['version'], build_number=args.build_number,
                                  workspace=str(workspace), upload_enabled=False,
                                  export_options=export_options(identity['team_id']),
                                  prerequisites=['Approved enrollment', 'App Store Connect app record using the existing bundle ID',
                                                 'Distribution signing assets', 'Captured source identity', 'Encryption compliance answers']), indent=2))
            return
        developer, _ = choose(installed())
        os.environ['DEVELOPER_DIR'] = developer
        env = dict(os.environ)
        if args.command == 'archive':
            archive_release(args, workspace, identity, env)
        else:
            export_release(workspace, env, upload=args.command == 'upload')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
