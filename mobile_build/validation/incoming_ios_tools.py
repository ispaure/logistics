"""Build and drive the Send File iOS source fixture on caller-owned simulators."""

from hashlib import sha256
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import signal
import subprocess
import tempfile
import time
from unicodedata import normalize
from uuid import UUID
from xml.etree import ElementTree as ET


SENDER_BUNDLE = 'io.github.ispaure.logisticsincomingsender'
TEST_BUNDLE = f'{SENDER_BUNDLE}.uitests'
RUNNER_BUNDLE = f'{TEST_BUNDLE}.xctrunner'
RECEIVER_BUNDLE = 'io.github.ispaure.logisticsinboxqa'
INCOMING_GROUP = 'group.io.github.ispaure.logisticsmobile'
SOURCES = Path(__file__).resolve().parents[1] / 'native_tests' / 'ios'
CASES = {
    'open-in': 'testOpenInActivatesMainApp',
    'files-open': 'testFilesOpenWithActivatesMainApp',
    'files-open-warm': 'testFilesOpenWithWarmMainApp',
    'files-open-resume': 'testFilesOpenWithResumesMainApp',
    'share': 'testShareExtensionReceivesTwoFiles',
    'share-open-reopen': 'testOpenAndReopenSharedFiles',
    'chooser-dismiss': 'testDismissShareChooser',
    'cancel': 'testCancelRemainingShareFiles',
    'duplicate': 'testShareKeepsBothFilesWithTheSameName',
    'provider-failure': 'testShareProviderFailsAfterFirstFile',
    'provider-retry': 'testShareRetryAfterProviderFailure',
}
DELIVERED = {
    'open-in': ('open-in',),
    'files-open': ('files-open',),
    'files-open-warm': ('warm',),
    'files-open-resume': ('resume',),
    'share': ('share', 'share-two'),
    'share-open-reopen': ('share', 'share-two'),
    'chooser-dismiss': (),
    'cancel': ('cancel-first',),
    'duplicate': ('duplicate-one', 'duplicate-two'),
    'provider-failure': ('failure-first',),
    'provider-retry': ('failure-second',),
}
DIRECT_OPEN_CASES = {'open-in', 'files-open', 'files-open-warm', 'files-open-resume'}
FILES_OPEN_CASES = DIRECT_OPEN_CASES - {'open-in'}
DIAGNOSTIC_CASES = {'ipad-window-controls': 'testInspectIPadWindowControls'}
ACCEPTANCE_CASES = {
    'iphone': ('chooser-dismiss', 'files-open', 'files-open-warm', 'share',
               'share-open-reopen', 'duplicate', 'cancel', 'provider-failure'),
    'ipad': ('files-open', 'share', 'share-open-reopen'),
}
IPHONE_SENDER_MODEL = 'com.apple.CoreSimulator.SimDeviceType.iPhone-18-Pro'


def _project_files(workspace):
    project = workspace / 'Sender.xcodeproj'
    project.mkdir(parents=True, exist_ok=True)
    objects = {}

    def put(label, kind, **properties):
        identifier = sha256(label.encode()).hexdigest()[:24].upper()
        objects[identifier] = dict(isa=kind, **properties)
        return identifier

    def configuration(name, settings):
        config = put(f'{name} Debug', 'XCBuildConfiguration', name='Debug', buildSettings=settings)
        return put(f'{name} configurations', 'XCConfigurationList', buildConfigurations=[config],
                   defaultConfigurationIsVisible='0', defaultConfigurationName='Debug')

    plist = workspace / 'Sender-Info.plist'
    plist.write_bytes(plistlib.dumps({
        'CFBundleDisplayName': 'Incoming Sender',
        'UIApplicationSceneManifest': {'UIApplicationSupportsMultipleScenes': False},
        'UILaunchScreen': {},
        'UIFileSharingEnabled': True,
        'LSSupportsOpeningDocumentsInPlace': True,
    }))
    products = []
    sources = []
    targets = []
    for name, filename, file_type, product_type, product, bundle in (
        ('Sender', 'IncomingSender.m', 'sourcecode.c.objc',
         'application', 'Sender.app', SENDER_BUNDLE),
        ('IntakeTests', 'IncomingFilesUITests.swift', 'sourcecode.swift',
         'bundle.ui-testing', 'IntakeTests.xctest', TEST_BUNDLE),
    ):
        snapshot = workspace / filename
        shutil.copyfile(SOURCES / filename, snapshot)
        source = put(filename, 'PBXFileReference', lastKnownFileType=file_type,
                     path=filename, sourceTree='<group>')
        sources.append(source)
        product_ref = put(product, 'PBXFileReference',
                          explicitFileType='wrapper.application' if name == 'Sender' else 'wrapper.cfbundle',
                          path=product, sourceTree='BUILT_PRODUCTS_DIR')
        products.append(product_ref)
        build_file = put(f'{filename} build file', 'PBXBuildFile', fileRef=source)
        build_sources = put(f'{name} sources', 'PBXSourcesBuildPhase', buildActionMask='2147483647',
                            files=[build_file], runOnlyForDeploymentPostprocessing='0')
        frameworks = put(f'{name} frameworks', 'PBXFrameworksBuildPhase', buildActionMask='2147483647',
                         files=[], runOnlyForDeploymentPostprocessing='0')
        settings = dict(PRODUCT_BUNDLE_IDENTIFIER=bundle, PRODUCT_NAME=name,
                        GENERATE_INFOPLIST_FILE='YES', CLANG_ENABLE_OBJC_ARC='YES',
                        CLANG_ENABLE_MODULES='YES', SWIFT_VERSION='5.0',
                        LD_RUNPATH_SEARCH_PATHS=['$(inherited)', '@executable_path/Frameworks',
                                                 '@loader_path/Frameworks'])
        if name == 'Sender':
            settings.update(INFOPLIST_FILE=plist.name,
                            OTHER_LDFLAGS=['-framework', 'UIKit', '-framework', 'UniformTypeIdentifiers'])
        else:
            settings['TEST_TARGET_NAME'] = 'Sender'
        targets.append(put(name, 'PBXNativeTarget', name=name, productName=name,
                           productReference=product_ref, productType=f'com.apple.product-type.{product_type}',
                           buildConfigurationList=configuration(name, settings),
                           buildPhases=[build_sources, frameworks], dependencies=[], buildRules=[]))

    product_group = put('Products', 'PBXGroup', name='Products', children=products, sourceTree='<group>')
    main_group = put('Main', 'PBXGroup', children=[*sources, product_group], sourceTree='<group>')
    sender_target, test_target = targets
    root = put('Project', 'PBXProject', compatibilityVersion='Xcode 14.0',
               buildConfigurationList=configuration('Project', dict(
                   SDKROOT='iphoneos', IPHONEOS_DEPLOYMENT_TARGET='15.0', TARGETED_DEVICE_FAMILY='1,2')),
               mainGroup=main_group, productRefGroup=product_group, targets=targets, projectDirPath='',
               projectRoot='', developmentRegion='en', knownRegions=['en'],
               attributes={'TargetAttributes': {test_target: {'TestTargetID': sender_target}}})
    proxy = put('Proxy', 'PBXContainerItemProxy', containerPortal=root, proxyType='1',
                remoteGlobalIDString=sender_target, remoteInfo='Sender')
    dependency = put('Dependency', 'PBXTargetDependency', target=sender_target, targetProxy=proxy)
    objects[test_target]['dependencies'].append(dependency)
    (project / 'project.pbxproj').write_bytes(plistlib.dumps(dict(
        archiveVersion='1', objectVersion='56', classes={}, objects=objects, rootObject=root)))

    def buildable(parent, identifier, name, product):
        ET.SubElement(parent, 'BuildableReference', BuildableIdentifier='primary',
                      BlueprintIdentifier=identifier, BuildableName=product, BlueprintName=name,
                      ReferencedContainer=f'container:{project.name}')

    scheme = ET.Element('Scheme', LastUpgradeVersion='1600', version='1.3')
    build = ET.SubElement(scheme, 'BuildAction', parallelizeBuildables='NO', buildImplicitDependencies='YES')
    build_entries = ET.SubElement(build, 'BuildActionEntries')
    for target, name, product in ((sender_target, 'Sender', 'Sender.app'),
                                  (test_target, 'IntakeTests', 'IntakeTests.xctest')):
        entry = ET.SubElement(build_entries, 'BuildActionEntry', buildForTesting='YES', buildForRunning='YES',
                              buildForProfiling='NO', buildForArchiving='NO', buildForAnalyzing='YES')
        buildable(entry, target, name, product)
    test = ET.SubElement(scheme, 'TestAction', buildConfiguration='Debug',
                         selectedDebuggerIdentifier='Xcode.DebuggerFoundation.Debugger.LLDB',
                         selectedLauncherIdentifier='Xcode.IDEFoundation.Launcher.LLDB')
    entry = ET.SubElement(ET.SubElement(test, 'Testables'), 'TestableReference', skipped='NO', parallelizable='NO')
    buildable(entry, test_target, 'IntakeTests', 'IntakeTests.xctest')
    directory = project / 'xcshareddata' / 'xcschemes'
    directory.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(scheme).write(directory / 'Intake.xcscheme', encoding='utf-8', xml_declaration=True)
    return project


def _xcodebuild(project, destination):
    return [
        'xcrun', 'xcodebuild', '-project', str(project), '-scheme', 'Intake',
        '-derivedDataPath', str(project.parent / 'DerivedData'),
        '-destination', destination, '-parallel-testing-enabled', 'NO',
        '-maximum-concurrent-test-simulator-destinations', '1',
        'CODE_SIGNING_ALLOWED=NO',
    ]


def _logged(command, environment, log, timeout, observe=None):
    with log.open('w', encoding='utf-8') as stream:
        stream.write(json.dumps(command) + '\n')
        stream.flush()
        with subprocess.Popen(command, env=environment, stdout=stream, stderr=subprocess.STDOUT,
                              start_new_session=True) as process:
            try:
                if observe is None:
                    return process.wait(timeout)
                deadline = time.monotonic() + timeout
                while process.poll() is None:
                    observe()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(command, timeout)
                    try:
                        return process.wait(min(0.1, remaining))
                    except subprocess.TimeoutExpired:
                        pass
                return process.returncode
            except BaseException:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(5)
                except subprocess.TimeoutExpired:
                    pass
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                raise


def _output(path):
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_sender(workspace, environment, output):
    """Generate and build the tiny sender and UI runner in the supplied workspace."""
    workspace = Path(tempfile.mkdtemp(prefix='incoming-ios-sender-', dir=Path(workspace).resolve(strict=True)))
    output = _output(output)
    project = _project_files(workspace)
    log = output / 'sender-build.log'
    command = [*_xcodebuild(project, 'generic/platform=iOS Simulator'), 'build-for-testing']
    if _logged(command, environment, log, timeout=300):
        raise RuntimeError(f'Sender build failed. See {log}')
    derived_data = workspace / 'DerivedData'
    app = derived_data / 'Build' / 'Products' / 'Debug-iphonesimulator' / 'Sender.app'
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    if (info.get('CFBundleIdentifier') != SENDER_BUNDLE
            or info.get('UIFileSharingEnabled') is not True
            or info.get('LSSupportsOpeningDocumentsInPlace') is not True):
        raise RuntimeError('The built sender lacks its required identity or Files integration')
    result = dict(project=str(project), app=str(app), derived_data=str(derived_data),
                  sender_bundle=SENDER_BUNDLE, runner_bundle=RUNNER_BUNDLE,
                  executable_sha256=sha256((app / info['CFBundleExecutable']).read_bytes()).hexdigest(),
                  sources={filename: sha256((workspace / filename).read_bytes()).hexdigest()
                           for filename in ('IncomingSender.m', 'IncomingFilesUITests.swift')})
    (output / 'sender-build.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def _udid(device):
    return str(UUID(str(device))).upper()


def _container(device, bundle, kind, environment):
    result = subprocess.run(
        ['xcrun', 'simctl', 'get_app_container', _udid(device), bundle, kind],
        env=environment, capture_output=True, text=True, timeout=20, check=True,
    )
    return Path(result.stdout.strip()).resolve(strict=True)


def _sender_documents(device, environment):
    return _container(device, SENDER_BUNDLE, 'data', environment) / 'Documents'


def _fixture_payloads(root):
    manifest = (root / 'manifest.json').read_bytes()
    metadata = json.loads(manifest)
    if metadata.get('version') != 1 or not metadata.get('fixtures'):
        raise ValueError(f'Invalid fixture manifest: {root}')
    payloads = {}
    filenames = {}
    for entry in metadata['fixtures']:
        fixture_id, name = entry['id'], entry['name']
        for component in (fixture_id, name):
            if not component or component in ('.', '..') or Path(component).name != component:
                raise ValueError(f'Unsafe fixture path: {component!r}')
        relative = Path(fixture_id) / name
        folder = root / fixture_id
        matching = [path for path in folder.iterdir()
                    if normalize('NFC', path.name) == normalize('NFC', name)]
        if len(matching) != 1 or matching[0].is_symlink() or not matching[0].is_file():
            raise ValueError(f'Fixture filename differs: {relative}')
        actual = matching[0]
        data = actual.read_bytes()
        if relative in payloads or len(data) != entry['length'] or sha256(data).hexdigest() != entry['sha256']:
            raise ValueError(f'Unexpected fixture bytes: {relative}')
        payloads[relative] = data
        filenames[fixture_id] = actual.name
    return manifest, metadata, payloads, filenames


def _write_new_or_verify(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('xb') as stream:
            stream.write(data)
    except FileExistsError:
        if path.read_bytes() != data:
            raise ValueError(f'Existing intake differs: {path}') from None


def transfer(sender_udid, receiver_udid, output, environment):
    """Copy exact payloads and index between the two source app Documents folders."""
    sender, receiver = _udid(sender_udid), _udid(receiver_udid)
    if sender == receiver:
        raise ValueError('The sender and receiver simulators must differ')
    source = _sender_documents(sender, environment) / 'Export'
    intake = _sender_documents(receiver, environment) / 'Intake'
    if source.parent == intake.parent:
        raise ValueError('The sender app containers must differ')
    deadline = time.monotonic() + 25
    while not (source / 'manifest.json').is_file():
        if time.monotonic() >= deadline:
            raise FileNotFoundError(f'Source app did not export its fixtures: {source}')
        time.sleep(0.25)
    manifest, _, payloads, _ = _fixture_payloads(source)
    for relative, data in payloads.items():
        _write_new_or_verify(intake / relative, data)
    _write_new_or_verify(intake / 'manifest.json', manifest)
    return verify_transfer(sender, receiver, output, environment, filename='transfer.json')


def verify_transfer(sender_udid, receiver_udid, output, environment, *, filename='source-postcheck.json'):
    """Read both source-app copies and record the manifest and byte comparison."""
    sender, receiver = _udid(sender_udid), _udid(receiver_udid)
    if sender == receiver:
        raise ValueError('The sender and receiver simulators must differ')
    source = _sender_documents(sender, environment) / 'Export'
    intake = _sender_documents(receiver, environment) / 'Intake'
    sender_manifest, metadata, sender_files, sender_names = _fixture_payloads(source)
    receiver_manifest, _, receiver_files, receiver_names = _fixture_payloads(intake)
    if sender_manifest != receiver_manifest or sender_files != receiver_files:
        raise ValueError('Source and intake copies differ')
    result = dict(sender=sender, receiver=receiver, bundle=SENDER_BUNDLE,
                  manifest_sha256=sha256(sender_manifest).hexdigest(), fixtures=metadata['fixtures'],
                  exact_bytes_match=True, canonical_filename_identity=True,
                  sender_raw_filenames=sender_names, receiver_source_raw_filenames=receiver_names)
    (_output(output) / filename).write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return result


def _file_digest(path):
    digest = sha256()
    length = 0
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
            length += len(block)
    return dict(length=length, sha256=digest.hexdigest())


def _queue_state(root):
    records = dict(exists=root.is_dir(), ready={}, partial={}, failure=False, producer=False)
    if root.is_dir():
        records['producer'] = (root / '.producer.lock').is_file()
        records['failure'] = (root / 'failed').is_file()
        for delivery in sorted(root.iterdir()):
            kind = delivery.suffix.removeprefix('.')
            if kind not in ('ready', 'partial') or delivery.is_symlink() or not delivery.is_dir():
                continue
            entry = {}
            try:
                payload = delivery / 'payload'
                if payload.is_file() and not payload.is_symlink():
                    entry.update(_file_digest(payload) if kind == 'ready' else dict(length=payload.stat().st_size))
                metadata = delivery / 'metadata.json'
                if metadata.is_file() and not metadata.is_symlink():
                    entry['raw_name'] = json.loads(metadata.read_bytes())['name']
                    entry['name'] = normalize('NFC', entry['raw_name'])
            except FileNotFoundError:
                # Publication or cancellation can retire a record during this read.
                continue
            if delivery.is_dir():
                records[kind][delivery.name] = entry
    return records


def _receiver_paths(device, environment):
    receiver = _udid(device)
    container = _container(receiver, RECEIVER_BUNDLE, 'data', environment)
    group = _container(receiver, RECEIVER_BUNDLE, INCOMING_GROUP, environment)
    return (container / 'Documents', container / 'Library/Application Support/Logistics/Incoming',
            group / 'Incoming')


def _receiver_state(device, paths):
    documents, main_queue, share_queue = paths
    publications = {}
    filenames = {}
    temporary = []
    if documents.is_dir():
        for path in sorted(documents.iterdir()):
            name = normalize('NFC', path.name)
            if name.startswith('.incoming-'):
                temporary.append(name)
            elif path.is_file() and not path.is_symlink():
                if name in filenames:
                    raise ValueError(f'Multiple published filenames share the same canonical identity: {name}')
                filenames[name] = path.name
                publications[name] = _file_digest(path)
    return dict(receiver=_udid(device), bundle=RECEIVER_BUNDLE, group=INCOMING_GROUP,
                publications=publications, publication_raw_filenames=filenames,
                publication_temporary=temporary, queues={
                    'main': _queue_state(main_queue),
                    'share': _queue_state(share_queue),
                })


def snapshot_receiver(device, output, environment, *, checkpoint='receiver-before'):
    """Record ordinary root files and both queues on the disposable QA receiver."""
    record = _receiver_state(device, _receiver_paths(device, environment))
    (_output(output) / f'{checkpoint}.json').write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return record


def _require_same_receiver(before, receiver):
    if before['receiver'] != receiver or before['bundle'] != RECEIVER_BUNDLE:
        raise ValueError('The publication baseline belongs to a different receiver')


def _expected_publications(fixtures, existing):
    destinations = {}
    for fixture in fixtures:
        name = normalize('NFC', fixture['name'])
        original = Path(name)
        number = 0
        while name in existing or name in destinations:
            number += 1
            name = f'{original.stem} ({number}){original.suffix}'
        destinations[name] = dict(id=fixture['id'], length=fixture['length'], sha256=fixture['sha256'])
    return destinations


def verify_publication(sender_udid, receiver_udid, case, before, output, environment, *,
                       checkpoint=None, already_published=False, prior_ready_fixtures=(), timeout=20):
    """Verify exact publications, earlier originals, both sources and clean queues."""
    receiver = _udid(receiver_udid)
    _require_same_receiver(before, receiver)
    checkpoint = checkpoint or f'{case}-publication'
    output = _output(output)
    transfer_record = verify_transfer(sender_udid, receiver, output, environment,
                                      filename=f'{checkpoint}-source-postcheck.json')
    fixture_index = {entry['id']: entry for entry in transfer_record['fixtures']}
    fixtures = [fixture_index[fixture_id] for fixture_id in (*prior_ready_fixtures, *DELIVERED[case])]
    existing = before['publications']
    expected = _expected_publications(fixtures, {} if already_published else existing)
    expected_digests = {name: {key: value for key, value in item.items() if key != 'id'}
                        for name, item in expected.items()}
    if already_published and any(existing.get(name) != digest for name, digest in expected_digests.items()):
        raise ValueError('The relaunch baseline does not contain the expected published originals')
    target_files = existing | expected_digests
    source = _sender_documents(sender_udid, environment) / 'Export'
    _, _, source_bytes, _ = _fixture_payloads(source)
    paths = _receiver_paths(receiver, environment)
    deadline = time.monotonic() + timeout
    while True:
        after = _receiver_state(receiver, paths)
        original_files_preserved = all(after['publications'].get(name) == entry for name, entry in existing.items())
        raw_before = before.get('publication_raw_filenames', {})
        raw_after = after['publication_raw_filenames']
        original_filenames_preserved = all(raw_after.get(name) == raw_name for name, raw_name in raw_before.items())
        complete = after['publications'] == target_files
        queues = after['queues']
        queue_drained = all(not queue['ready'] and not queue['failure'] for queue in queues.values())
        partials_absent = not after['publication_temporary'] and all(not queue['partial'] for queue in queues.values())
        if (complete and queue_drained and partials_absent) or time.monotonic() >= deadline:
            break
        time.sleep(0.25)

    matches = {}
    filename_identity = {}
    for name, entry in expected.items():
        fixture = fixture_index[entry['id']]
        raw_name = raw_after.get(name)
        filename_identity[name] = raw_name is not None and normalize('NFC', raw_name) == name
        path = paths[0] / (raw_name or name)
        payload = source_bytes[Path(fixture['id']) / fixture['name']]
        matches[name] = path.is_file() and not path.is_symlink() and path.read_bytes() == payload
    queue_route_matches = True
    if case in DIRECT_OPEN_CASES:
        queue_route_matches = (after['queues']['main']['producer']
                               and after['queues']['share'] == before['queues']['share'])
    elif case == 'chooser-dismiss':
        queue_route_matches = after['queues'] == before['queues']
    canonical_names_match = all(filename_identity.values())
    passed = (complete and original_files_preserved and original_filenames_preserved
              and canonical_names_match and all(matches.values()) and queue_drained
              and partials_absent and queue_route_matches)
    result = dict(case=case, passed=passed, before=before, after=after, expected=expected,
                  exact_bytes_match=matches, prior_publications_preserved=original_files_preserved,
                  prior_raw_filenames_preserved=original_filenames_preserved,
                  canonical_filename_identity=canonical_names_match, filename_identity=filename_identity,
                  source_raw_filenames=dict(sender=transfer_record['sender_raw_filenames'],
                                            receiver=transfer_record['receiver_source_raw_filenames']),
                  exactly_expected_publications=complete, queues_drained=queue_drained,
                  partials_absent=partials_absent, queue_route_matches=queue_route_matches, source_originals_match=True,
                  observation='cooperative source delivery; 24-hour force-kill expiry outside this check')
    (output / f'{checkpoint}.json').write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    if not passed:
        raise AssertionError(f'Unexpected iOS publications or queue state. See {output / (checkpoint + ".json")}')
    return result


def verify_share_handoff(sender_udid, receiver_udid, before, output, environment):
    """Verify two new complete extension handoffs while the main receiver is stopped."""
    receiver = _udid(receiver_udid)
    _require_same_receiver(before, receiver)
    output = _output(output)
    source = verify_transfer(sender_udid, receiver, output, environment, filename='share-handoff-source.json')
    fixtures = {item['id']: item for item in source['fixtures']}
    expected = {normalize('NFC', fixtures[key]['name']): {name: fixtures[key][name] for name in ('sha256', 'length')}
                for key in DELIVERED['share']}
    after = _receiver_state(receiver, _receiver_paths(receiver, environment))
    main, share = after['queues']['main'], after['queues']['share']
    previous = before['queues']['share']['ready']
    added = {key: record for key, record in share['ready'].items() if key not in previous}
    ready = {record.get('name'): {key: record.get(key) for key in ('sha256', 'length')}
             for record in added.values()}
    passed = (ready == expected and len(added) == len(expected)
              and all(share['ready'].get(key) == record for key, record in previous.items())
              and not main['ready'] and not main['partial'] and not share['partial']
              and not main['failure'] and not share['failure']
              and before['publications'] == after['publications'] and not after['publication_temporary'])
    receipt = output / 'share-handoff.json'
    receipt.write_text(json.dumps(dict(passed=passed, before=before, after=after, expected=expected,
                                      canonical_filename_identity=ready.keys() == expected.keys()),
                                  indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    if not passed:
        raise AssertionError(f'Unexpected extension handoff. See {receipt}')
    return after


def run_case(project, device, case, output, environment, *, observe=None):
    """Run one named XCTest on exactly the supplied simulator and retain its result."""
    project, device = Path(project).resolve(strict=True), _udid(device)
    test = (CASES | DIAGNOSTIC_CASES)[case]
    output = _output(output)
    log, bundle = output / f'{case}.log', output / f'{case}.xcresult'
    # On iOS 27.0, each Files context-menu action can consume XCTest's
    # 60-second animation wait before automation proceeds normally.
    files_menu = case in FILES_OPEN_CASES
    allowance, timeout = (420, 480) if files_menu else (220, 300)
    command = [
        *_xcodebuild(project, f'platform=iOS Simulator,id={device}'),
        '-collect-test-diagnostics', 'never',
        '-test-timeouts-enabled', 'YES', '-maximum-test-execution-time-allowance', str(allowance),
    ]
    if files_menu:
        command.extend(('-default-test-execution-time-allowance', str(allowance)))
    command.extend(('-resultBundlePath', str(bundle), '-only-testing:IntakeTests/IncomingFilesUITests/' + test,
                    'test-without-building'))
    try:
        returncode = _logged(command, environment, log, timeout=timeout, observe=observe)
    except subprocess.TimeoutExpired:
        with log.open('a', encoding='utf-8') as stream:
            stream.write(f'\nThe targeted XCTest command exceeded its {timeout}-second timeout.\n')
        returncode = 124
    result = dict(case=case, test=test, device=device, returncode=returncode,
                  log=str(log), result_bundle=str(bundle) if bundle.is_dir() else None)
    (output / f'{case}.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def verify_window_routing(xctest, publication, output):
    """Bind the iPad two-window UI proof to one verified main-route publication."""
    receipt = Path(output) / 'window-routing.json'
    result = dict(status='failed', acceptance=True, case='files-open',
                  xctest=xctest, publication=str(Path(output) / 'files-open-publication.json'))
    try:
        lines = Path(xctest['log']).read_text(encoding='utf-8').splitlines()
        markers = [index for index, line in enumerate(lines)
                   if line == '[IncomingFiles] ipad-window-routing-proof']
        if len(markers) != 1 or markers[0] + 1 >= len(lines):
            raise ValueError('Expected one complete iPad window-routing proof marker.')
        proof = json.loads(lines[markers[0] + 1])
        expected = dict(schema=3, route='files-open-with', windows_before=2, windows_after=3,
                        active_window_after_delivery='new-home', primary_app_settings_preserved=True,
                        secondary_app_settings_preserved=True, restart_before_read=True,
                        read_window='primary-after-restart',
                        opened_from_on_my_tablet=True, reopened_from_on_my_tablet=True)
        added = set(publication['after']['publications']) - set(publication['before']['publications'])
        if (xctest['returncode'] != 0 or xctest['case'] != 'files-open'
                or xctest['test'] != CASES['files-open'] or proof != expected
                or not publication['passed'] or not publication['queue_route_matches']
                or len(publication['expected']) != 1 or len(added) != 1
                or {item['id'] for item in publication['expected'].values()} != {'files-open'}):
            raise ValueError('Window proof requires the passing iPad UI case and one exact main-route publication.')
        result.update(status='passed', proof=proof, publication_names=sorted(added),
                      xctest_log_sha256=sha256(Path(xctest['log']).read_bytes()).hexdigest(),
                      scope='Observed OS-created main Home window and preserved original Settings windows; native callback session IDs not inferred.')
    except Exception as error:
        result['error'] = repr(error)
        raise
    finally:
        receipt.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return result


def save_window_delivery_observation(xctest, output):
    """Keep scene observations even if a later reader check fails; never accept the case here."""
    lines = Path(xctest['log']).read_text(encoding='utf-8').splitlines()
    markers = [index for index, line in enumerate(lines)
               if line == '[IncomingFiles] ipad-window-delivery-proof']
    proof = None
    if len(markers) == 1 and markers[0] + 1 < len(lines):
        try:
            proof = json.loads(lines[markers[0] + 1])
        except ValueError:
            pass
    record = dict(acceptance=False, proof=proof, xctest_returncode=xctest['returncode'],
                  xctest_log_sha256=sha256(Path(xctest['log']).read_bytes()).hexdigest(),
                  scope='Scene observation only; final routing acceptance also requires exact publication and reader/restart checks.')
    (Path(output) / 'window-delivery-observation.json').write_text(json.dumps(record, indent=2) + '\n')


class ProviderObservation:
    """Read the source telemetry and receiver queues while the second representation is held."""

    def __init__(self, device, case, fixtures, before, output, environment):
        self.device, self.case = device, case
        self.mode = 'failure' if case == 'provider-failure' else 'cancel'
        self.before, self.output = before, Path(output)
        self.paths = _receiver_paths(device, environment)
        self.telemetry = _sender_documents(device, environment) / 'ProviderEvidence' / f'{self.mode}.json'
        self.environment = environment
        self.next_container_check = 0
        self.telemetry_paths = [str(self.telemetry)]
        self.container_errors = []
        self.binding = None
        self.fixtures = [next(item for item in fixtures if item['id'] == f'{self.mode}-{part}')
                         for part in ('first', 'second')]
        self.held = None

    def refresh_source_container(self, *, force=False):
        if self.telemetry.is_file() or (not force and time.monotonic() < self.next_container_check):
            return
        self.next_container_check = time.monotonic() + 1
        try:
            # XCTest may reinstall its target after the suite's initial install.
            # Resolve that source app again instead of retaining its old data UUID.
            current = _sender_documents(self.device, self.environment) / 'ProviderEvidence' / f'{self.mode}.json'
            if str(current) != self.telemetry_paths[-1]:
                self.telemetry_paths.append(str(current))
            self.telemetry = current
        except (subprocess.SubprocessError, FileNotFoundError) as error:
            self.container_errors = [*self.container_errors[-7:], repr(error)]

    def observe(self):
        if self.held is not None:
            return
        self.refresh_source_container()
        if not self.telemetry.is_file():
            return
        data = self.telemetry.read_bytes()
        evidence = json.loads(data)
        if self.binding is None:
            if evidence.get('schema') != 1 or evidence.get('mode') != self.mode:
                raise ValueError('The source telemetry does not identify this provider case.')
            self.binding = dict(device=self.device, source_bundle=SENDER_BUNDLE,
                                telemetry_path=str(self.telemetry), initial_sha256=sha256(data).hexdigest(),
                                initial_evidence=evidence, resolved_paths=list(self.telemetry_paths))
            (self.output / f'{self.case}-provider-binding.json').write_text(
                json.dumps(self.binding, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        events = evidence['events']
        if [event['event'] for event in events] != ['prepared', 'armed', 'requested']:
            return
        state = _receiver_state(self.device, self.paths)
        # A second atomic telemetry read brackets the snapshot before release/cancellation.
        following = json.loads(self.telemetry.read_bytes())
        if following['events'] != events:
            return
        first = self.fixtures[0]
        main, share = state['queues']['main'], state['queues']['share']
        previous = self.before['queues']['share']['ready']
        added = {key: item for key, item in share['ready'].items() if key not in previous}
        expected = dict(name=normalize('NFC', first['name']), length=first['length'], sha256=first['sha256'])
        ready = [{key: item.get(key) for key in expected} for item in added.values()]
        if (ready != [expected] or main != self.before['queues']['main']
                or any(share['ready'].get(key) != item for key, item in previous.items())
                or share['partial'] or share['failure'] or state['publication_temporary']
                or state['publications'] != self.before['publications']
                or state['publication_raw_filenames'] != self.before['publication_raw_filenames']):
            return
        self.held = dict(passed=True, telemetry_before=evidence, telemetry_after=following,
                         receiver=state, expected_first=expected,
                         observation='Exact first Share ready record saved before acknowledging the source fixture; main queue and ordinary root unchanged.')
        self.save()
        # Acknowledge only in the source fixture's private telemetry directory.
        # XCTest waits for the source to observe this before Cancel/release.
        acknowledgement = self.telemetry.with_name(f'{self.mode}-checkpoint.json')
        temporary = acknowledgement.with_suffix('.tmp')
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(dict(schema=1, mode=self.mode, requested_uptime=events[-1]['uptime']), stream)
        temporary.replace(acknowledgement)

    def save(self):
        self.refresh_source_container(force=True)
        telemetry = json.loads(self.telemetry.read_bytes()) if self.telemetry.is_file() else None
        record = dict(case=self.case, mode=self.mode, telemetry=telemetry, held_checkpoint=self.held,
                      binding=self.binding, resolved_telemetry_paths=self.telemetry_paths,
                      container_errors=self.container_errors,
                      source_documents_present=self.telemetry.parent.parent.is_dir())
        (self.output / f'{self.case}-provider-observation.json').write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        return record

    def verify(self, xctest):
        result = self.save()
        result['passed'] = False
        try:
            telemetry = result['telemetry']
            events = telemetry['events']
            names = [event['event'] for event in events]
            allowed_terminal = {'released', 'cancelled'} if self.mode == 'cancel' else {'released'}
            if (telemetry['schema'] != 1 or telemetry['mode'] != self.mode or self.held is None
                    or self.binding is None
                    or len(events) != 5 or names[:4] != ['prepared', 'armed', 'requested', 'checkpoint-observed']
                    or names[-1] not in allowed_terminal):
                raise ValueError('Expected one armed, selected, held request and an explicit terminal event.')
            items = telemetry['items']
            if len(items) != 2:
                raise ValueError('Expected the two concrete file provider inventories.')
            for item, fixture in zip(items, self.fixtures):
                candidate = item['candidate']
                if (normalize('NFC', item['filename']) != normalize('NFC', fixture['name'])
                        or not item['content_type'] or candidate['first_data_type'] != item['content_type']
                        or item['content_type'] not in candidate['registered_types']
                        or 'public.file-url' not in candidate['registered_types']
                        or candidate['registered_types'].index(item['content_type'])
                           >= candidate['registered_types'].index('public.file-url')
                        or not candidate['file_url_conformance']
                        or 'public.file-url' not in item['url_writable_types']):
                    raise ValueError('The candidate must offer the actual file content before its file URL.')
            lines = Path(xctest['log']).read_text(encoding='utf-8').splitlines()
            times = {}
            for phase in ('selection-start', 'held-main-stopped', 'action-start'):
                marker = f'[IncomingFiles] {self.mode}-provider-{phase}'
                indices = [index for index, line in enumerate(lines) if line == marker]
                if len(indices) != 1 or indices[0] + 1 >= len(lines):
                    raise ValueError(f'Missing or ambiguous provider {phase} timestamp.')
                times[phase] = float(lines[indices[0] + 1])
            prepared, armed, requested, checkpoint, terminal = [event['uptime'] for event in events]
            if not (prepared <= armed <= times['selection-start'] <= requested
                    <= times['held-main-stopped'] <= times['action-start'] <= terminal
                    and requested <= checkpoint <= times['action-start']):
                raise ValueError('The held content request must follow selection while the main app remains stopped.')
            if xctest['returncode'] != 0:
                raise ValueError('Provider acceptance requires a passing native UI test.')
            result.update(passed=True, native_uptime=times)
        except Exception as error:
            result['error'] = repr(error)
            raise
        finally:
            (self.output / f'{self.case}-provider-verification.json').write_text(
                json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        return result


def _suite_artifacts(receiver, sender, scratch, output):
    from logistics_build.incoming_acceptance import verify_ios
    from logistics_build.ios_backend import bundle_digest

    if (receiver['platform'] != 'ios' or receiver['bundle'] != RECEIVER_BUNDLE
            or receiver['status'] != 'built' or receiver.get('workspace_removed')):
        raise ValueError('The receiver build receipt must identify a retained normal-entry iOS QA app.')
    if sender['sender_bundle'] != SENDER_BUNDLE or sender['runner_bundle'] != RUNNER_BUNDLE:
        raise ValueError('The sender build receipt must identify the disposable source app and UI runner.')
    receiver_app = Path(receiver['app']).resolve(strict=True)
    sender_app = Path(sender['app']).resolve(strict=True)
    project = Path(sender['project']).resolve(strict=True)
    if not all(path.is_relative_to(scratch) for path in (receiver_app, sender_app, project)):
        raise ValueError('The suite build receipts must share the retained receiver scratch workspace.')
    if verify_ios(receiver_app) != receiver['identity'] or bundle_digest(receiver_app) != receiver['bundle_sha256']:
        raise ValueError('The receiver app no longer matches its normal-entry build receipt.')
    sender_info = plistlib.loads((sender_app / 'Info.plist').read_bytes())
    if (sender_info.get('CFBundleIdentifier') != SENDER_BUNDLE
            or sender_info.get('UIFileSharingEnabled') is not True
            or sender_info.get('LSSupportsOpeningDocumentsInPlace') is not True
            or _file_digest(sender_app / sender_info['CFBundleExecutable'])['sha256'] != sender['executable_sha256']):
        raise ValueError('The sender app no longer matches its build receipt.')
    source_output = output / 'sender-sources'
    source_output.mkdir()
    for filename in ('IncomingSender.m', 'IncomingFilesUITests.swift'):
        source = (project.parent / filename).read_bytes()
        if sha256(source).hexdigest() != sender['sources'][filename]:
            raise ValueError(f'Frozen sender source differs from its build receipt: {filename}')
        (source_output / filename).write_bytes(source)
    return receiver_app, sender_app, project


def _suite_case(report, save, project, source, destination, case, output, environment):
    row = dict(case=case, status='running')
    report['cases'].append(row)
    report['pending_cases'].remove(case)
    save()
    print(f'Running iOS {report["profile"]} case: {case}', flush=True)
    provider = None
    try:
        before = snapshot_receiver(destination, output, environment, checkpoint=f'{case}-before')
        row['before'] = str(output / f'{case}-before.json')
        if case in ('cancel', 'provider-failure'):
            provider = ProviderObservation(destination, case, report['transfer']['fixtures'], before, output, environment)
        row['xctest'] = run_case(project, destination, case, output, environment,
                                 observe=provider.observe if provider else None)
        if report['profile'] == 'ipad' and case == 'files-open':
            save_window_delivery_observation(row['xctest'], output)
        if row['xctest']['returncode'] or not row['xctest']['result_bundle']:
            raise RuntimeError(f'XCTest failed for {case}. See {row["xctest"]["log"]}')
        if provider:
            row['provider_verification'] = str(output / f'{case}-provider-verification.json')
            provider.verify(row['xctest'])
        if case == 'share':
            row['verification'] = str(output / 'share-handoff.json')
            verify_share_handoff(source, destination, before, output, environment)
        else:
            row['verification'] = str(output / f'{case}-publication.json')
            publication = verify_publication(source, destination, case, before, output, environment)
            if report['profile'] == 'ipad' and case == 'files-open':
                row['window_routing'] = str(output / 'window-routing.json')
                verify_window_routing(row['xctest'], publication, output)
                report['window_routing'] = 'passed'
        row['status'] = 'passed'
    except BaseException as error:
        row.update(status='failed', error=repr(error))
        if report['profile'] == 'ipad' and case == 'files-open':
            report['window_routing'] = 'failed'
        raise
    finally:
        try:
            if provider:
                provider.save()
                row['provider_observation'] = str(output / f'{case}-provider-observation.json')
            snapshot_receiver(destination, output, environment, checkpoint=f'{case}-after')
            row['after'] = str(output / f'{case}-after.json')
        except Exception as snapshot_error:
            row['snapshot_error'] = repr(snapshot_error)
            if row['status'] == 'passed':
                row.update(status='failed', error=repr(snapshot_error))
                raise
        finally:
            save()


def run_suite(receiver, sender, workspace, output, *, profile='iphone', model, runtime, environment=None):
    """Run the native file intake cases on a fresh, owned simulator pair."""
    from build_manager.apple_simulators import AppleSimulators
    from build_manager.locking import operation_lock_path, workspace_lock
    from build_manager.retention import lease
    from logistics_build.build_retention import owned_scratch
    from logistics_build.incoming_acceptance import cleanup_ios, create_ios

    if profile not in ACCEPTANCE_CASES:
        raise ValueError('Choose the iphone or ipad receiver profile.')
    cases = ACCEPTANCE_CASES[profile]
    workspace = Path(workspace).absolute()
    if (any(path.is_symlink() for path in (workspace, *workspace.parents))
            or not re.fullmatch(r'simulators-[0-9a-f]{32}', workspace.name)
            or tuple(workspace.parent.parts[-4:]) != ('.tools', 'build-manager', 'workspaces', 'ios')):
        raise ValueError('Choose a fresh workspace under the manager’s iOS simulator workspace directory.')
    scratch = Path(receiver['workspace']).resolve(strict=True)
    output = _output(output)
    result_path = output / 'result.json'
    if result_path.exists():
        raise ValueError(f'Choose a fresh suite evidence location: {output}')
    env = dict(os.environ, **(environment or {}))
    client = AppleSimulators(env)
    source_model = model if profile == 'iphone' else IPHONE_SENDER_MODEL
    report = dict(schema=1, profile=profile, model=model, sender_model=source_model, runtime=runtime,
                  workspace=str(workspace), receiver=receiver, sender=sender, status='running',
                  window_routing='pending' if profile == 'ipad' else 'not_applicable',
                  window_routing_profile='ipad',
                  devices=[], cases=[], pending_cases=list(cases))

    def save():
        temporary = result_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        temporary.replace(result_path)

    with workspace_lock(operation_lock_path(workspace)), lease(scratch):
        if not owned_scratch(scratch):
            raise ValueError('The suite requires a retained Logistics build workspace.')
        if result_path.exists():
            raise ValueError(f'Choose a fresh suite evidence location: {output}')
        if workspace.exists() and any(workspace.iterdir()):
            raise ValueError(f'Choose a fresh suite simulator workspace: {workspace}')
        save()
        failure = None
        try:
            receiver_app, sender_app, project = _suite_artifacts(receiver, sender, scratch, output)
            report['toolchain'] = client.toolchain()
            report['developer_dir'] = env.get('DEVELOPER_DIR')
            for role, device_model in (('sender', source_model), (profile, model)):
                row = create_ios(client, workspace, role, device_model, runtime)
                report['devices'].append(row)
                save()
                print(f'Booting owned iOS {role}: {row["device"]}', flush=True)
                client.boot(row['device'], name=row['name'])
                client.invoke('install', row['device'], str(sender_app), timeout=180)
            source, destination = (row['device'] for row in report['devices'])
            client.invoke('install', destination, str(receiver_app), timeout=180)
            client.invoke('launch', source, SENDER_BUNDLE, '--export-fixtures')
            report['transfer'] = transfer(source, destination, output, env)
            save()
            for case in cases:
                _suite_case(report, save, project, source, destination, case, output, env)
            report['status'] = 'passed'
        except BaseException as error:
            failure = error
            report.update(status='cancelled' if isinstance(error, KeyboardInterrupt) else 'failed', error=repr(error))
            raise
        finally:
            try:
                if 'transfer' in report:
                    report['source_postcheck'] = verify_transfer(source, destination, output, env)
                    if report['source_postcheck'] != report['transfer']:
                        raise ValueError('One or both source-app copies differ from the initial transfer.')
            except Exception as error:
                report.update(source_postcheck_error=repr(error), status='failed')
                if failure is None:
                    failure = error
                else:
                    failure.add_note(f'Source postcheck failed: {error}')
            finally:
                try:
                    report['cleanup'] = cleanup_ios(client, workspace, output / 'cleanup.json')
                    cleaned = {row['device'] for row in report['cleanup']
                               if row['removed'] and not row.get('temporary_apps_remaining')}
                    if any(row['device'] not in cleaned for row in report['devices']):
                        raise RuntimeError('Cleanup did not verify removal of every acquired simulator.')
                except Exception as error:
                    cleanup_path = output / 'cleanup.json'
                    if 'cleanup' not in report and cleanup_path.is_file():
                        try:
                            report['cleanup'] = json.loads(cleanup_path.read_text(encoding='utf-8'))
                        except (OSError, ValueError) as receipt_error:
                            report['cleanup_receipt_error'] = repr(receipt_error)
                    report.update(cleanup_error=repr(error), status='failed')
                    if failure is None:
                        failure = error
                    else:
                        failure.add_note(f'Simulator cleanup failed: {error}')
                finally:
                    save()
        if failure is not None:
            raise failure
    return report
