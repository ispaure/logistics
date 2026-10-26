"""Distribute a specific uploaded iOS build to the configured external group."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import time
from uuid import UUID

from build_manager.app_store_connect import (
    API as API, NoRedirect as NoRedirect, AppStoreConnectClient, SigningDependencyError,
    token as signing_token, wait_for_processed_build,
)

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / 'testflight-distribution.json'
AUTH = ROOT / '.testflight-auth.json'
BUNDLE = 'io.github.ispaure.logisticsmobile'


def settings():
    value = json.loads(SETTINGS.read_text())
    from .manager_settings import distribution
    value = distribution(ROOT, 'testflight', value)
    if value['bundle_id'] != BUNDLE or not str(value['app_id']).isdigit():
        raise ValueError('External distribution must use the existing Logistics app.')
    if not value['external_group'].strip() or not value['what_to_test'].strip():
        raise ValueError('Configure an external group and What to Test information.')
    if not 1 <= value['poll_interval_seconds'] <= 60 or not 1 <= value['processing_timeout_seconds'] <= 3600:
        raise ValueError('Invalid processing wait limits.')
    return value


def credentials():
    reference = auth_reference()
    saved = json.loads(reference.read_text()) if reference.exists() else {}
    if AUTH == ROOT / '.testflight-auth.json':
        from .manager_settings import authentication_references
        profile = authentication_references(ROOT)
        if profile.get('auth.key_reference'):
            saved['key_path'] = profile['auth.key_reference']
    value = {name: os.environ.get(env) or saved.get(name)
             for name, env in [('key_path', 'ASC_KEY_PATH'), ('key_id', 'ASC_KEY_ID'), ('issuer_id', 'ASC_ISSUER_ID')]}
    if not all(value.values()):
        raise ValueError('External TestFlight distribution needs an App Store Connect team API key. '
                         'Configure mobile_build/deployment/testflight_external.py or set ASC_KEY_PATH, ASC_KEY_ID and ASC_ISSUER_ID.')
    if not re.fullmatch(r'[A-Z0-9]{10}', value['key_id']):
        raise ValueError('Invalid App Store Connect key ID.')
    UUID(value['issuer_id'])
    if not Path(value['key_path']).is_file():
        raise ValueError('App Store Connect private key file is missing.')
    return value


def auth_reference():
    if AUTH != ROOT / '.testflight-auth.json':
        return AUTH
    from .manager_settings import authentication_references
    return Path(authentication_references(ROOT).get('auth.testflight_reference') or AUTH)


def token(auth, now=None):
    try:
        return signing_token(auth, now=now)
    except SigningDependencyError:
        raise ValueError('Install mobile_build/requirements-testflight.txt in the build environment.') from None


class Client(AppStoreConnectClient):
    """Keep the established project import while using the reusable transport."""
    def __init__(self, auth):
        super().__init__(auth, token_factory=token)


def target(client, config):
    app = client.request('GET', '/v1/apps/' + config['app_id'])['data']
    if app['attributes']['bundleId'] != BUNDLE:
        raise ValueError('Configured App Store Connect app has a different bundle ID.')
    matches = [g for g in client.list('/v1/apps/' + app['id'] + '/betaGroups', limit=200)
               if g['attributes']['name'] == config['external_group'] and g['attributes']['isInternalGroup'] is False]
    if len(matches) != 1:
        raise ValueError('Expected exactly one existing external TestFlight group named ' + config['external_group'] + '.')
    return matches[0]


def prepare():
    config = settings()
    if not config['enabled']:
        return None
    client = Client(credentials())
    return client, config, target(client, config)


def wait_for_build(client, config, number, version, *, sleep=time.sleep, clock=time.monotonic):
    def validate(build):
        attrs = build['attributes']
        if attrs.get('expired') or attrs.get('buildAudienceType') == 'INTERNAL_ONLY':
            raise ValueError('Expired or internal-only build cannot be distributed externally.')
    return wait_for_processed_build(client, app_id=config['app_id'], number=number, version=version,
        platform='IOS', timeout=config['processing_timeout_seconds'], interval=config['poll_interval_seconds'],
        validate=validate, progress=lambda: print('Waiting for Apple to process iOS ' + version + ' (' + number + ')…', flush=True),
        sleep=sleep, clock=clock)


def distribute(workspace, prepared=None):
    prepared = prepared or prepare()
    if prepared is None:
        return
    client, config, group = prepared
    record = json.loads((workspace / 'release.json').read_text())
    if record['identity']['bundle_id'] != BUNDLE:
        raise ValueError('Release metadata belongs to another app.')
    build = record['build']
    report = dict(app_id=config['app_id'], group_name=config['external_group'], group_id=group['id'],
                  version=build['version'], build_number=build['build_number'], status='pending')
    def save():
        (workspace / 'external-distribution.json').write_text(json.dumps(report, indent=2) + '\n')
    try:
        save()
        found = wait_for_build(client, config, build['build_number'], build['version'])
        build_id = found['id']
        report['build_id'] = build_id
        detail = client.request('GET', '/v1/builds/' + build_id + '/buildBetaDetail')['data']
        state = detail['attributes']['externalBuildState']
        report['external_state'] = state
        allowed = {'READY_FOR_BETA_SUBMISSION', 'WAITING_FOR_BETA_REVIEW', 'IN_BETA_REVIEW',
                   'BETA_APPROVED', 'READY_FOR_BETA_TESTING', 'IN_BETA_TESTING'}
        if state not in allowed:
            raise ValueError('External testing needs attention in App Store Connect: ' + state +
                             '. Complete encryption/review requirements there, then run distribute again.')
        localizations = client.list('/v1/builds/' + build_id + '/betaBuildLocalizations', limit=200)
        existing = [v for v in localizations if v['attributes']['locale'] == config['locale']]
        if len(existing) > 1:
            raise ValueError('Ambiguous beta build localization.')
        if existing:
            # Preserve per-build notes entered by the owner.
            if not (existing[0]['attributes'].get('whatsNew') or '').strip():
                client.request('PATCH', '/v1/betaBuildLocalizations/' + existing[0]['id'], body={'data': {
                    'type': 'betaBuildLocalizations', 'id': existing[0]['id'],
                    'attributes': {'whatsNew': config['what_to_test']}}})
        else:
            client.request('POST', '/v1/betaBuildLocalizations', body={'data': {
                'type': 'betaBuildLocalizations', 'attributes': {'locale': config['locale'], 'whatsNew': config['what_to_test']},
                'relationships': {'build': {'data': {'type': 'builds', 'id': build_id}}}}})
        client.request('PATCH', '/v1/buildBetaDetails/' + detail['id'], body={'data': {
            'type': 'buildBetaDetails', 'id': detail['id'], 'attributes': {'autoNotifyEnabled': True}}})
        if state == 'READY_FOR_BETA_SUBMISSION':
            client.request('POST', '/v1/betaAppReviewSubmissions', body={'data': {
                'type': 'betaAppReviewSubmissions', 'relationships': {'build': {'data': {'type': 'builds', 'id': build_id}}}}})
            report['review_submitted'] = True
        else:
            report['review_submitted'] = False
        # Relationship POST is additive; never remove the group's earlier builds.
        linked = client.list('/v1/betaGroups/' + group['id'] + '/relationships/builds', limit=200)
        if not any(item['id'] == build_id for item in linked):
            client.request('POST', '/v1/betaGroups/' + group['id'] + '/relationships/builds',
                           body={'data': [{'type': 'builds', 'id': build_id}]})
        linked = client.list('/v1/betaGroups/' + group['id'] + '/relationships/builds', limit=200)
        if not any(item['id'] == build_id for item in linked):
            raise RuntimeError('Apple has not confirmed the build in the external group. Retry distribute.')
        report['status'] = 'assigned'
        save()
        print('Assigned ' + build['version'] + ' (' + build['build_number'] + ') to ' + group['attributes']['name'] +
              '; automatic tester notification enabled. Apple beta review may still be pending.')
    except (ValueError, RuntimeError) as error:
        report.update(status='needs_attention', error=str(error))
        save()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('configure', 'check'))
    parser.add_argument('--key-path', type=Path)
    parser.add_argument('--key-id')
    parser.add_argument('--issuer-id')
    args = parser.parse_args()
    if args.command == 'configure':
        if not args.key_path or not args.key_id or not args.issuer_id:
            parser.error('configure needs --key-path, --key-id and --issuer-id; never paste the private key.')
        key = args.key_path.expanduser().resolve()
        if not key.is_file() or not re.fullmatch(r'[A-Z0-9]{10}', args.key_id):
            raise ValueError('Missing key file or invalid key ID.')
        UUID(args.issuer_id)
        value = dict(key_path=str(key), key_id=args.key_id, issuer_id=args.issuer_id)
        token(value)
        with open(AUTH, 'w', opener=lambda path, flags: os.open(path, flags, 0o600)) as output:
            json.dump(value, output, indent=2)
        AUTH.chmod(0o600)
        print('Saved local API key reference. Run check to verify app and external group access.')
    else:
        prepared = prepare()
        print('External distribution is disabled.' if prepared is None else
              'Verified API access to Logistics and external group ' + prepared[1]['external_group'] + '.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        sys.exit(str(error))
