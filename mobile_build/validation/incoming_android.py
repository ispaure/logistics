"""SendFile06 native Sharesheet checks for a pair of leased Android emulators."""
import argparse
from dataclasses import dataclass
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import time
from uuid import uuid4
from xml.etree import ElementTree as ET


SENDER = 'io.github.ispaure.logisticsincomingsender'
RECEIVER = 'io.github.ispaure.logisticsinboxqa'
MAIN_PACKAGE = 'io.github.ispaure.logisticsmobile'
RECEIVE_ACTIVITY = 'io.github.ispaure.logisticsmobile.ReceiveActivity'
SOURCE = Path(__file__).resolve().parents[1] / 'native_tests/android/incoming'
FIXTURES = 'files/fixtures'
DESTINATION = 'files/data/Files'
QUEUE = 'no_backup/Incoming'


@dataclass(frozen=True)
class Scenario:
    items: tuple
    lifecycle: str = 'warm'
    action: str = 'deliver'


SCENARIOS = {
    'cold-single': Scenario(('cold',), 'cold'),
    'warm-multiple': Scenario(('warm-a', 'warm-b')),
    'background-resume': Scenario(('resume',), 'background'),
    'duplicate': Scenario(('duplicate-a', 'duplicate-b')),
    'chooser-cancel': Scenario(('dismiss',), 'cold', 'dismiss'),
    'receiver-cancel': Scenario(('cancel-first', 'cancel-second'), 'cold', 'cancel'),
    'source-error': Scenario(('error-first', 'error-second'), 'cold', 'error'),
    'receiver-interrupted': Scenario(('leave-first', 'leave-second'), 'cold', 'leave'),
    'receiver-death': Scenario(('death-first', 'death-second'), 'cold', 'death'),
}
CASES = tuple(SCENARIOS)
MODELS = {'phone': 'pixel_9', 'tablet': 'pixel_tablet'}
SUITE_MARKER = 'sendfile06-android-suite.json'


def digest(contents):
    return {'bytes': len(contents), 'sha256': sha256(contents).hexdigest()}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def build_sender(workspace, sdk, java, output):
    """Build in a caller-owned disposable workspace and record the sender APK hash."""
    project = Path(workspace).resolve() / 'sendfile06-sender'
    sdk, java, output = (Path(path).resolve() for path in (sdk, java, output))
    project.mkdir(parents=True)
    output.mkdir(parents=True, exist_ok=True)
    classes = project / 'classes'
    classes.mkdir()
    for name in ('AndroidManifest.xml', 'IncomingSender.java'):
        shutil.copyfile(SOURCE / name, project / name)
    platform = sdk / 'platforms/android-36/android.jar'
    versions = sorted((path for path in (sdk / 'build-tools').iterdir()
                       if re.fullmatch(r'\d+(\.\d+)+', path.name)),
                      key=lambda path: tuple(map(int, path.name.split('.'))))
    require(versions, f'No Android build tools installed under {sdk}')
    tools = versions[-1]
    env = dict(os.environ, JAVA_HOME=str(java), PATH=str(java / 'bin') + os.pathsep + os.environ['PATH'])

    def build(*args):
        with (output / 'sender-build.log').open('ab') as log:
            log.write(('$ ' + shlex.join(map(str, args)) + '\n').encode())
            log.flush()
            subprocess.run(args, cwd=project, env=env, timeout=90, check=True,
                           stdout=log, stderr=subprocess.STDOUT)

    (output / 'sender-build.log').write_bytes(b'')
    build(tools / 'aapt2', 'link', '--manifest', 'AndroidManifest.xml', '-I', platform,
          '-o', 'resources.apk')
    build(java / 'bin/javac', '--release', '8', '-classpath', platform, '-d', classes,
          'IncomingSender.java')
    build(tools / 'd8', '--min-api', '26', '--lib', platform, '--output', project,
          *sorted(classes.rglob('*.class')))
    build(tools / 'aapt', 'add', 'resources.apk', 'classes.dex')
    build(tools / 'zipalign', '-f', '4', 'resources.apk', 'aligned.apk')
    build(java / 'bin/keytool', '-genkeypair', '-keystore', 'debug.jks',
          '-storepass', 'android', '-keypass', 'android', '-alias', 'androiddebugkey',
          '-keyalg', 'RSA', '-dname', 'CN=Disposable SendFile06 Sender', '-validity', '7')
    apk = project / 'sender.apk'
    build(tools / 'apksigner', 'sign', '--ks', 'debug.jks', '--ks-pass', 'pass:android',
          '--out', apk, 'aligned.apk')
    build(tools / 'apksigner', 'verify', '--verbose', apk)
    build(tools / 'aapt', 'dump', 'badging', apk)
    badging = (output / 'sender-build.log').read_text(errors='replace')
    require(f"package: name='{SENDER}'" in badging and '\napplication-debuggable\n' in badging,
            'The sender APK must have the disposable package identity and allow run-as')
    write_json(output / 'sender-apk.json', dict(apk=str(apk), package=SENDER, sdk=str(sdk),
               java=str(java), build_tools=tools.name, **digest(apk.read_bytes()),
               sources={name: digest((project / name).read_bytes())
                        for name in ('AndroidManifest.xml', 'IncomingSender.java')}))
    return apk


class Device:
    """All ADB calls use one explicit, verified manager-owned AVD serial."""

    def __init__(self, adb, serial, avd, output):
        require(re.fullmatch(r'emulator-\d+', serial), f'Expected an emulator serial: {serial}')
        require(re.fullmatch(r'build-manager-[a-f0-9]{32}', avd), f'Expected an owned AVD name: {avd}')
        self.adb, self.serial, self.avd = str(adb), serial, avd
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.verify()

    def call(self, *args, check=True, data=None, timeout=20):
        command = [self.adb, '-s', self.serial, *args]
        with (self.output / 'adb-commands.log').open('a', encoding='utf-8') as log:
            log.write(shlex.join(command) + '\n')
        result = subprocess.run(command, input=data, capture_output=True, timeout=timeout)
        if check and result.returncode:
            error = (result.stderr or result.stdout).decode(errors='replace').strip()
            raise RuntimeError(f'{shlex.join(command)} failed ({result.returncode}): {error}')
        return result

    def verify(self):
        names = self.call('emu', 'avd', 'name').stdout.decode().splitlines()
        require(names and names[0].strip() == self.avd,
                f'{self.serial} does not identify leased AVD {self.avd}')

    def shell(self, *args, check=True, data=None, timeout=20):
        return self.call('shell', '-T', '-e', 'none', shlex.join(args),
                         check=check, data=data, timeout=timeout)

    def read(self, package, path):
        self.shell('run-as', package, 'test', '-f', path)
        return self.call('exec-out', 'run-as', package, 'cat', path).stdout

    def read_state(self, script):
        return self.shell('run-as', RECEIVER, 'sh', '-c', script).stdout.decode()

    def sender_write(self, path, data):
        # POSIX shell stdin without a PTY preserves NUL, CR and trailing newlines.
        require(re.fullmatch(r'files/(?:fixtures/[a-z-]+/(?:name|payload)|gates/[a-f0-9]{32})', path),
                f'Invalid sender file: {path}')
        parent = shlex.quote(str(Path(path).parent))
        name = shlex.quote(path)
        self.shell('run-as', SENDER, 'sh', '-c',
                   f'mkdir -p {parent} && cat > {name}.relay && mv {name}.relay {name}', data=data)

    def property(self, name):
        return self.shell('getprop', name).stdout.decode().strip()

    def identity(self):
        return dict(serial=self.serial, avd=self.avd, sdk=self.property('ro.build.version.sdk'),
                    fingerprint=self.property('ro.build.fingerprint'), model=self.property('ro.product.model'))

    def start(self, component, *extras):
        self.verify()
        action = () if component.startswith(SENDER + '/') else (
            '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.LAUNCHER')
        result = self.shell('am', 'start', '-W', *action, '-n', component, *extras, timeout=45)
        report = result.stdout.decode(errors='replace')
        require('Error:' not in report and 'Exception' not in report, report)
        return report

    def launcher(self):
        result = self.shell('cmd', 'package', 'resolve-activity', '--brief', '-a',
                            'android.intent.action.MAIN', '-c', 'android.intent.category.LAUNCHER',
                            RECEIVER).stdout.decode()
        names = [line.strip() for line in result.splitlines() if line.strip().startswith(RECEIVER + '/')]
        require(len(names) == 1 and not names[0].endswith(RECEIVE_ACTIVITY),
                f'Cannot resolve normal launcher for {RECEIVER}: {result}')
        return names[0]

    def pid(self):
        # Package ownership is authoritative even when pidof cannot see an
        # app's argv or Android has just marked its Activity resumed.
        uid = self.shell('run-as', RECEIVER, 'id', '-u').stdout.decode().strip()
        require(uid.isdecimal() and int(uid) >= 10000, f'Unexpected receiver UID: {uid!r}')
        rows = self.shell('ps', '-A', '-o', 'UID,PID').stdout.decode().splitlines()
        require(rows and rows[0].split() == ['UID', 'PID'], 'Cannot inspect Android processes')
        pids = [pid for owner, pid in (line.split() for line in rows[1:]) if owner == uid]
        require(len(pids) <= 1 and all(pid.isdecimal() for pid in pids),
                f'Ambiguous receiver process for UID {uid}: {pids}')
        return pids[0] if pids else None

    def process_evidence(self, checkpoint):
        report = self.shell('ps', '-A', '-o', 'PID,UID,NAME,ARGS').stdout
        (self.output / f'{checkpoint}-process-table.txt').write_bytes(report)
        report = self.shell('dumpsys', 'activity', 'processes', RECEIVER).stdout
        (self.output / f'{checkpoint}-receiver-processes.txt').write_bytes(report)

    def foreground(self):
        result = self.shell('dumpsys', 'activity', 'activities').stdout.decode(errors='replace')
        lines = [line.strip() for line in result.splitlines() if 'topResumedActivity=ActivityRecord' in line]
        if not lines:
            lines = [line.strip() for line in result.splitlines()
                     if line.strip().startswith('ResumedActivity: ActivityRecord')]
        require(len(lines) <= 1, f'Cannot resolve the top resumed activity: {lines}')
        return lines[0] if lines else ''

    def wait_foreground(self, component):
        def focused():
            foreground = self.foreground()
            return foreground if component in foreground else None

        return wait_for(f'{component} in the foreground', focused)

    def force_stop(self):
        self.verify()
        self.shell('am', 'force-stop', RECEIVER)
        wait_for('receiver process to stop', lambda: self.pid() is None)

    def key(self, name):
        self.shell('input', 'keyevent', name)

    def screenshot(self, name):
        path = self.output / f'{name}.png'
        path.write_bytes(self.call('exec-out', 'screencap', '-p').stdout)

    def hierarchy(self, name):
        remote = '/data/local/tmp/logistics-sendfile06.xml'
        self.shell('rm', '-f', remote)
        try:
            self.shell('uiautomator', 'dump', remote, timeout=15)
            data = self.call('exec-out', 'cat', remote).stdout
        finally:
            self.shell('rm', '-f', remote)
        (self.output / f'{name}.xml').write_bytes(data)
        return ET.fromstring(data)

    def queue(self):
        data = self.read_state(f'if [ -d {QUEUE} ]; then '
                               f'for d in {QUEUE}/*.partial {QUEUE}/*.ready; do '
                               '[ -d "$d" ] || continue; '
                               'size=0; [ ! -f "$d/payload" ] || size=$(stat -c %s "$d/payload"); '
                               'printf "%s %s\\n" "${d##*/}" "$size"; done; fi')
        return {name: int(size) for name, size in (line.split() for line in data.splitlines())}

    def published(self):
        names = self.published_names()
        return {name: digest(self.read(RECEIVER, f'{DESTINATION}/{name}')) for name in names}

    def published_names(self):
        data = self.read_state(f'if [ -d {DESTINATION} ]; then '
                               f'find {DESTINATION} -maxdepth 1 -type f -print; fi')
        names = sorted(Path(path).name for path in data.splitlines())
        require(len(names) <= 100 and all(re.fullmatch(
            r'SF06 \d\d [A-Za-z ]+(?: \(\d+\))?\.txt|\.incoming-[a-f0-9-]+\.ready', name)
            for name in names), f'Unexpected contents in disposable receiver root: {names}')
        return names

    def provider_log(self):
        return self.shell('logcat', '-d', '-v', 'brief', '-s',
                          'LogisticsInboxSender:I', '*:S').stdout.decode(errors='replace')


def wait_for(description, callback, timeout=35):
    deadline = time.monotonic() + timeout
    while True:
        value = callback()
        if value is not None and value is not False:
            return value
        if time.monotonic() >= deadline:
            raise RuntimeError(f'Timed out waiting for {description}')
        time.sleep(0.25)


def devices(sender_serial, receiver_serial, adb, output, sender_avd, receiver_avd):
    require(sender_serial != receiver_serial and sender_avd != receiver_avd,
            'Sender and receiver must be distinct leased AVDs')
    return (Device(adb, sender_serial, sender_avd, Path(output) / 'sender'),
            Device(adb, receiver_serial, receiver_avd, Path(output)))


def fixture(device, item):
    name = device.read(SENDER, f'{FIXTURES}/{item}/name').decode('utf-8')
    require(re.fullmatch(r'SF06 \d\d [A-Za-z ]+\.txt', name), f'Invalid fixture display name: {name!r}')
    contents = device.read(SENDER, f'{FIXTURES}/{item}/payload')
    require(contents.startswith(f'SendFile06 marker {item}\n'.encode()),
            f'Fixture marker missing in {item} on {device.serial}')
    return name, contents


def source_record(device, item):
    name, data = fixture(device, item)
    return dict(name=name, **digest(data))


def source_records(sender, receiver, items):
    return {item: {'sender': source_record(sender, item), 'receiver_source': source_record(receiver, item)}
            for item in items}


def ready_handoff(receiver, ready, original):
    name, contents = original
    payload = receiver.read(RECEIVER, f'{QUEUE}/{ready}/payload')
    metadata = json.loads(receiver.read(RECEIVER, f'{QUEUE}/{ready}/metadata.json'))
    require(payload == contents, 'Completed first handoff differs from its source')
    require(metadata == {'name': name}, 'Completed handoff name differs from its source')
    return dict(name=name, **digest(payload))


def transfer(sender_serial, receiver_serial, adb, output, *, sender_avd, receiver_avd):
    """Seed source bytes in the sender app, relay, and re-read them at both endpoints."""
    output = Path(output)
    sender, receiver = devices(sender_serial, receiver_serial, adb, output, sender_avd, receiver_avd)
    result = dict(sender=sender.identity(), receiver=receiver.identity(), fixtures={})
    result['seed'] = sender.start(SENDER + '/.IncomingSender', '--ez', 'seed', 'true')
    # am start -W can report before onCreate finishes generating the originals.
    items = [item for case in SCENARIOS.values() for item in case.items]
    last_payload = f'{FIXTURES}/{items[-1]}/payload'
    wait_for('sender seed completion', lambda: sender.shell(
        'run-as', SENDER, 'test', '-s', last_payload, check=False).returncode == 0)
    receiver.verify()
    for item in items:
        name, contents = fixture(sender, item)
        receiver.sender_write(f'{FIXTURES}/{item}/name', name.encode())
        receiver.sender_write(f'{FIXTURES}/{item}/payload', contents)
        copy = fixture(receiver, item)
        require(copy == (name, contents) == fixture(sender, item), f'Binary relay changed {item}')
        result['fixtures'][item] = dict(display_name=name, sender=digest(contents), receiver=digest(copy[1]))
    write_json(output / 'transfer.json', result)
    return result


def values(node):
    return (node.get('text', ''), node.get('content-desc', ''))


def matches(node, *labels):
    return any(' '.join(value.split()).casefold() == label.casefold()
               for value in values(node) for label in labels)


def enabled(node):
    return node.get('enabled') == 'true'


def owned(node):
    return node.get('package') == RECEIVER


def wait_ui(device, name, find, timeout=30):
    def inspect():
        try:
            tree = device.hierarchy(name)
        except (RuntimeError, ET.ParseError, subprocess.TimeoutExpired):
            return None
        return find(tree)

    return wait_for(f'UI checkpoint {name}', inspect, timeout)


def one_node(tree, predicate):
    nodes = [node for node in tree.iter('node') if enabled(node) and predicate(node)]
    require(len(nodes) <= 1, f'Ambiguous UI target: {[node.attrib for node in nodes]}')
    return nodes[0] if nodes else None


def chooser_target(tree, package):
    """Resolve a unique app cell even if its label is a separate child node."""
    parents = {child: parent for parent in tree.iter('node') for child in parent}
    targets = set()
    for node in tree.iter('node'):
        if node.get('package') != package or not matches(node, 'Logisticks'):
            continue
        cell = node
        while cell is not None and cell.get('clickable') != 'true':
            cell = parents.get(cell)
        if cell is not None and enabled(cell):
            targets.add(cell)
    require(len(targets) <= 1, f'Ambiguous Logisticks Sharesheet cells: {[node.attrib for node in targets]}')
    return next(iter(targets), None)


def bounds(node):
    matched = re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', node.get('bounds', ''))
    require(matched, f'Invalid UI bounds: {node.attrib}')
    left, top, right, bottom = map(int, matched.groups())
    require(right > left and bottom > top, f'UI target has no touch area: {node.attrib}')
    return left, top, right, bottom


def tap(device, node):
    left, top, right, bottom = bounds(node)
    device.shell('input', 'tap', str((left + right) // 2), str((top + bottom) // 2))


def control(device, checkpoint, predicate):
    node = wait_ui(device, checkpoint, lambda tree: one_node(tree, predicate))
    device.screenshot(checkpoint)
    tap(device, node)


def workspaces(device, label, prefix):
    def source_tab(node):
        return (owned(node) and node.get('class', '').endswith('Button')
                and matches(node, 'Local', 'Local selected'))

    def workspace_control(node):
        return (owned(node) and matches(node, 'Workspaces') and node.get('clickable') == 'true')

    def browser_control(tree):
        if not any(owned(node) and matches(node, 'File and folder actions') for node in tree.iter('node')):
            return None
        return one_node(tree, lambda node: owned(node) and matches(node, 'Back', 'Back to Workspaces'))

    def entry(tree):
        node = one_node(tree, source_tab)
        if node is not None:
            return node
        node = one_node(tree, lambda node: owned(node) and matches(node, 'Close document'))
        if node is not None:
            return node
        node = browser_control(tree)
        return node if node is not None else one_node(tree, workspace_control)

    node = wait_ui(device, prefix + '-workspaces', entry, timeout=90)
    device.screenshot(prefix + '-workspaces')
    if matches(node, 'Close document'):
        tap(device, node)
        node = wait_ui(device, prefix + '-reader-closed', lambda tree: (
            None if any(owned(candidate) and matches(candidate, 'Close document')
                        for candidate in tree.iter('node')) else entry(tree)))
    if not source_tab(node):
        tap(device, node)
    control(device, prefix + '-local', source_tab)

    def device_tab(node):
        return owned(node) and (
            matches(node, label + ' selected') or
            (matches(node, label) and node.get('content-desc', '').casefold() == label.casefold()
             and node.get('class', '').endswith('Button')))

    control(device, prefix + '-device-tab', device_tab)
    control(device, prefix + '-device-root', lambda node: (
        owned(node) and matches(node, label)
        and node.get('content-desc', '').casefold().startswith(label.casefold() + ', ')))
    wait_ui(device, prefix + '-ordinary-root', lambda tree: any(
        owned(node) and matches(node, label) and not node.get('class', '').endswith('Button')
        for node in tree.iter('node')) and one_node(
            tree, lambda node: owned(node) and matches(node, 'File and folder actions')))
    device.screenshot(prefix + '-ordinary-root')


def open_row(device, name, item, prefix):
    def locate(tree):
        for suffix in ('. File', '. Document'):
            node = one_node(tree, lambda node: owned(node) and matches(node, name + suffix))
            if node is not None:
                return node
        return one_node(tree, lambda node: owned(node) and matches(node, name))

    tree = wait_ui(device, prefix + '-file-row', lambda tree: tree)
    node = locate(tree)
    if node is None:
        # Use the normal browser's search when the recycled list does not show
        # the row in its current viewport.
        control(device, prefix + '-search', lambda node: owned(node) and matches(node, 'Search this folder'))
        # The leading fixture identifier is enough to find a numbered copy and
        # keeps Android's input tool from interpreting parenthesized suffixes.
        device.shell('input', 'text', name[:7].replace(' ', '%s'))
        node = wait_ui(device, prefix + '-file-row', locate)
    device.screenshot(prefix + '-file-row')
    tap(device, node)

    marker = f'SendFile06 marker {item}'

    def opened(tree):
        nodes = [node for node in tree.iter('node') if owned(node)]
        title = any(matches(node, name) for node in nodes)
        visible_content = any(marker in value for node in nodes for value in values(node))
        return title and visible_content

    wait_ui(device, prefix + '-reader', opened, timeout=45)
    device.screenshot(prefix + '-reader')


def verify_route(device, label, expected, prefix):
    if not expected:
        workspaces(device, label, prefix)
    for index, (name, item) in enumerate(expected.items()):
        checkpoint = f'{prefix}-{index + 1}'
        workspaces(device, label, checkpoint)
        open_row(device, name, item, checkpoint)


def expect_additions(previous, originals, items):
    expected = {}
    occupied = set(previous)
    for item in items:
        name = originals[item][0]
        stem, suffix = Path(name).stem, Path(name).suffix
        new_name = name
        number = 0
        while new_name in occupied:
            number += 1
            new_name = f'{stem} ({number}){suffix}'
        occupied.add(new_name)
        expected[new_name] = item
    return expected


def admitted_items(snapshot, expected, originals):
    """Match complete files by name and bytes; a native queue can drain out of order."""
    pending = set(expected.values())
    admitted = {}
    for name, expected_item in expected.items():
        display_name = originals[expected_item][0]
        matching = [item for item in pending if originals[item][0] == display_name
                    and digest(originals[item][1]) == snapshot.get(name)]
        require(len(matching) == 1, f'Wrong or ambiguous published bytes for {name}')
        admitted[name] = matching[0]
        pending.remove(matching[0])
    return admitted


def run_case(case, sender_serial, receiver_serial, adb, output, *, sender_avd,
             receiver_avd, tablet=False, launcher=None):
    """Run one end-to-end case with the preinstalled apps and previously relayed originals."""
    scenario = SCENARIOS[case]
    output = Path(output)
    sender, receiver = devices(sender_serial, receiver_serial, adb, output, sender_avd, receiver_avd)
    label = 'On My Tablet' if tablet else 'On My Phone'
    installed_launcher = receiver.launcher()
    require(launcher is None or launcher == installed_launcher,
            f'Expected the installed normal launcher {installed_launcher}: {launcher}')
    launcher = installed_launcher
    token = uuid4().hex
    action = scenario.action
    gated = action in {'cancel', 'error', 'leave', 'death'}
    result = dict(case=case, lifecycle=scenario.lifecycle, action=action, launcher=launcher,
                  sender=sender.identity(), receiver=receiver.identity(), route_label=label,
                  token=token, success=False)
    originals = {}

    try:
        for item in scenario.items:
            source = fixture(sender, item)
            require(fixture(receiver, item) == source, f'Relayed original differs for {item}')
            originals[item] = source
        if case == 'duplicate':
            first, second = originals.values()
            require(first[0] == second[0] and first[1] != second[1], 'Duplicate fixture identities are invalid')
        result['originals_before'] = {
            item: {endpoint: dict(name=name, **digest(data)) for endpoint in ('sender', 'receiver_source')}
            for item, (name, data) in originals.items()
        }
        before = receiver.published()
        queue_before = receiver.queue()
        require(not any(name.endswith('.ready') for name in queue_before),
                f'Prior ready records must drain before the case: {queue_before}')
        result.update(published_before=before, queue_before=queue_before)
        saved = () if action == 'dismiss' else scenario.items[:1] if gated else scenario.items
        expected = expect_additions(before, originals, saved)

        if scenario.lifecycle == 'cold':
            receiver.force_stop()
        else:
            result['warm_launch'] = receiver.start(launcher)
            foreground = receiver.wait_foreground(RECEIVER + '/')
            require(RECEIVER + '/' in foreground and RECEIVE_ACTIVITY not in foreground, foreground)
            result['warm_foreground'] = foreground
            pid = wait_for('warm receiver process', receiver.pid)
            wait_ui(receiver, 'warm-normal-ui', lambda tree: any(
                owned(node) and matches(node, 'Workspaces', 'Close document')
                for node in tree.iter('node')), timeout=90)
            require(receiver.pid() == pid and pid, 'Warm app did not stay alive during startup')
            if scenario.lifecycle == 'background':
                receiver.key('KEYCODE_HOME')
                wait_for('Home to background the normal app',
                         lambda: RECEIVER + '/' not in receiver.foreground())
                result['background_foreground'] = receiver.foreground()
        result['pid_before_chooser'] = receiver.pid()
        require(bool(result['pid_before_chooser']) == (scenario.lifecycle != 'cold'),
                'Unexpected receiver process state before chooser')
        receiver.process_evidence('before-chooser')

        mode = 'error' if action == 'error' else 'slow' if gated else 'plain'
        result['intent_action'] = ('ACTION_SEND' if len(scenario.items) == 1 else 'ACTION_SEND_MULTIPLE')
        result['uris'] = [f'content://{SENDER}.files/{item}/{mode if index else "plain"}/{token}'
                          for index, item in enumerate(scenario.items)]
        result['share_launch'] = receiver.start(SENDER + '/.IncomingSender',
                                                '--es', 'items', ','.join(scenario.items),
                                                '--es', 'token', token, '--es', 'mode', mode)
        result['chooser_activity'] = receiver.wait_foreground('ChooserActivity')
        chooser_package = re.search(r'\bu\d+ ([A-Za-z0-9_.]+)/', result['chooser_activity'])
        require(chooser_package, f'Cannot resolve Sharesheet package: {result["chooser_activity"]}')
        target = wait_ui(receiver, 'sharesheet', lambda tree: chooser_target(tree, chooser_package[1]))
        receiver.screenshot('sharesheet')
        result['chooser_target'] = dict(target.attrib)
        if action == 'dismiss':
            receiver.key('KEYCODE_BACK')
            wait_for('system Sharesheet dismissal', lambda: 'ChooserActivity' not in receiver.foreground())
            receiver.screenshot('chooser-dismissed')
            require(receiver.pid() is None, 'Dismissed chooser started Logistics')
            require(receiver.queue() == queue_before and receiver.published() == before,
                    'Dismissed chooser changed intake or publication')
            result['launch_after_dismiss'] = receiver.start(launcher)
        else:
            tap(receiver, target)
            result['native_foreground'] = receiver.wait_foreground(RECEIVE_ACTIVITY)
            result['pid_during_receive'] = wait_for('native receiver process', receiver.pid)
            receiver.process_evidence('during-receive')
            if scenario.lifecycle != 'cold':
                require(result['pid_during_receive'] == result['pid_before_chooser'],
                        'Warm delivery replaced the receiver process')

            if gated:
                def prefix_staged():
                    current = receiver.queue()
                    partials = {name: size for name, size in current.items()
                                if name not in queue_before and name.endswith('.partial')}
                    ready = [name for name in current if name not in queue_before and name.endswith('.ready')]
                    if len(partials) == 1 and list(partials.values()) == [4096] and len(ready) == 1:
                        return current
                    return None

                pending = wait_for('completed first file and second item staged at its source gate', prefix_staged)
                result['queue_while_second_blocked'] = pending
                partial = next(name for name in pending if name not in queue_before and name.endswith('.partial'))
                ready = next(name for name in pending if name not in queue_before and name.endswith('.ready'))
                require(receiver.read(RECEIVER, f'{QUEUE}/{partial}/payload') == originals[scenario.items[1]][1][:4096],
                        'Gated receiver bytes differ from the source prefix')
                first_original = originals[scenario.items[0]]
                result['ready_while_second_blocked'] = ready_handoff(receiver, ready, first_original)
                receiver.hierarchy('native-second-blocked')
                receiver.screenshot('native-second-blocked')
                if action == 'cancel':
                    control(receiver, 'native-cancel', lambda node: owned(node) and matches(node, 'Cancel remaining files'))
                elif action == 'leave':
                    receiver.key('KEYCODE_BACK')
                    wait_for('user to leave native receiver', lambda: RECEIVE_ACTIVITY not in receiver.foreground())
                elif action == 'death':
                    receiver.verify()
                    require(receiver.pid() == result['pid_during_receive'],
                            'Receiver process changed before interruption')
                    receiver.shell('run-as', RECEIVER, 'kill', '-9', result['pid_during_receive'])
                    wait_for('receiver process death', lambda: receiver.pid() != result['pid_during_receive'])
                    result['queue_after_death'] = receiver.queue()
                    require(result['queue_after_death'] == pending, 'Hard death changed completed/partial handoffs')
                receiver.sender_write(f'files/gates/{token}', b'go\n')
                if action == 'error':
                    wait_for('source to send a reliable pipe error',
                             lambda: f'source-error {token}' in receiver.provider_log())

            if action in {'leave', 'death'}:
                if action == 'leave':
                    wait_for('native partial cleanup after leaving the activity',
                             lambda: not any(name not in queue_before and name.endswith('.partial')
                                             for name in receiver.queue()))
                result['launch_after_interruption'] = receiver.start(launcher)
            else:
                def native_status(tree):
                    return next((node.get('text') for node in tree.iter('node')
                                 if owned(node) and (node.get('text') or '').startswith(f'{len(saved)} file(s) received.')
                                 and label in node.get('text')), None)

                status = wait_ui(receiver, 'native-complete', native_status)
                require(('Remaining files cancelled.' in status) == (action == 'cancel'), status)
                require(('Some files could not be received' in status) == (action == 'error'), status)
                result['native_status'] = status
                receiver.screenshot('native-complete')
                if action in {'cancel', 'error'}:
                    terminal = dict(status=status, foreground=receiver.foreground(), queue=receiver.queue())
                    result['native_before_open'] = terminal
                    require(RECEIVE_ACTIVITY in terminal['foreground'], 'Native receiver left before queue inspection')
                    require(terminal['queue'] == {**queue_before, ready: pending[ready]},
                            f'Terminal native queue should retain only the first completed handoff: {terminal["queue"]}')
                    terminal['ready'] = ready_handoff(receiver, ready, first_original)
                    terminal['originals'] = source_records(sender, receiver, originals)
                    require(terminal['originals'] == result['originals_before'], 'Sender or relayed original changed')
                    write_json(output / 'native-before-open.json', terminal)
                control(receiver, 'open-logisticks', lambda node: owned(node) and matches(node, 'Open Logisticks'))
                if scenario.lifecycle != 'cold':
                    require(receiver.pid() == result['pid_before_chooser'], 'Normal launcher replaced the warm process')

        wait_for('new files in the ordinary root', lambda: set(expected).issubset(receiver.published_names()))
        snapshot = receiver.published()
        require(set(snapshot) == set(before) | set(expected), f'Unexpected publication names: {snapshot}')
        require(all(snapshot[name] == old for name, old in before.items()), 'Existing publications changed')
        opened = admitted_items(snapshot, expected, originals)
        result['published'] = snapshot
        verify_route(receiver, label, opened, 'delivered')
        result['opened'] = opened

        receiver.force_stop()
        result['relaunch'] = receiver.start(launcher)
        verify_route(receiver, label, opened, 'reopened')
        require(receiver.published() == snapshot, 'Publication changed after reopen')
        result['published_after_reopen'] = snapshot
        final_queue = receiver.queue()
        allowed = set(queue_before)
        if action == 'death':
            allowed.add(partial)
            require(final_queue.get(partial) == 4096, 'Hard-death partial did not retain its observed prefix')
        require(set(final_queue) <= allowed, f'Unexpected native staging after reopen: {final_queue}')
        result['queue_after_reopen'] = final_queue

        after = source_records(sender, receiver, originals)
        result['originals_after_reopen'] = after
        require(after == result['originals_before'], 'Sender or relayed original changed')
        result['success'] = True
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        write_json(output / 'result.json', result)
        for name, capture in (
            ('failure-screen', lambda: receiver.screenshot('failure-screen') if not result['success'] else None),
            ('failure-ui', lambda: receiver.hierarchy('failure-ui') if not result['success'] else None),
            ('failure-processes', lambda: receiver.process_evidence('failure') if not result['success'] else None),
            ('provider-log', lambda: (output / 'provider.log').write_text(receiver.provider_log(), encoding='utf-8')),
            ('final-files', lambda: write_json(output / 'final-files.json', receiver.published())),
            ('final-queue', lambda: write_json(output / 'final-queue.json', receiver.queue())),
        ):
            try:
                capture()
            except Exception as error:
                with (output / 'evidence-errors.log').open('a', encoding='utf-8') as log:
                    log.write(f'{name}: {error}\n')
    return result


def _suite_emulators(sender, workspace, profile, environment):
    from build_manager.android_emulators import AndroidEmulator
    from build_manager.retention import linked

    require(profile in MODELS, f'Unknown Android receiver profile: {profile}')
    env = dict(environment or {}, JAVA_HOME=sender['java'])
    env['PATH'] = str(Path(sender['java']) / 'bin') + os.pathsep + env.get('PATH', os.environ['PATH'])
    require(not any(linked(workspace / role) for role in ('sender', profile)),
            f'Linked Android emulator workspace under {workspace}')
    require(not any(linked(workspace / role / 'lease.json') for role in ('sender', profile)),
            f'Linked Android emulator lease under {workspace}')
    return {role: AndroidEmulator(sender['sdk'], workspace / role, environment=env)
            for role in ('sender', profile)}


def _suite_workspace(workspace):
    from build_manager.retention import linked

    workspace = Path(workspace).absolute()
    suffix = ('mobile_build', '.tools', 'build-manager', 'workspaces', 'android')
    require(workspace.parent.parts[-len(suffix):] == suffix
            and re.fullmatch(r'incoming-[a-f0-9]{32}', workspace.name)
            and '..' not in workspace.parts
            and not any(linked(path) for path in (workspace, *workspace.parents)),
            f'Expected a canonical disposable Android workspace: {workspace}')
    return workspace.resolve()


def _packages(emulator, record):
    emulator.verify(record)
    report = emulator.invoke('-s', record['serial'], 'shell', 'pm', 'list', 'packages')
    packages = {line.removeprefix('package:') for line in report.splitlines() if line.startswith('package:')}
    require(packages, f'No package inventory returned by {record["serial"]}')
    return packages


def _install(emulator, record, apk, package, output):
    require(MAIN_PACKAGE not in _packages(emulator, record), 'The main Logistics app is on this emulator')
    serial = record['serial']
    log = emulator.invoke('-s', serial, 'install', str(apk), timeout=180)
    output.mkdir(parents=True, exist_ok=True)
    (output / f'install-{package}.log').write_text(log + '\n', encoding='utf-8')
    require(package in _packages(emulator, record), f'Installed APK did not register as {package}')


def _cleanup_emulator(emulator, role, output):
    result = dict(role=role, workspace=str(emulator.workspace), removed=False, uninstalled=[])
    removed = emulator.workspace / 'removed-lease.json'
    log = emulator.workspace / 'emulator.log'
    preserve = False
    packages = None
    try:
        if emulator.marker.is_file():
            record = json.loads(emulator.marker.read_text())
            result.update(serial=record['serial'], name=record['name'])
            packages = _packages(emulator, record)
            if MAIN_PACKAGE in packages:
                preserve = True
                raise RuntimeError('Main Logistics app detected; the emulator and its data were preserved')
            for package in (RECEIVER, SENDER):
                if package in packages:
                    emulator.invoke('-s', record['serial'], 'uninstall', package)
                    result['uninstalled'].append(package)
    except Exception as error:
        result['package_cleanup_error'] = str(error)
    finally:
        if packages is not None:
            try:
                remaining = _packages(emulator, record) & {SENDER, RECEIVER}
                result['temporary_apps_remaining'] = sorted(remaining)
                require(not remaining, f'Temporary packages remain on {record["serial"]}: {sorted(remaining)}')
            except Exception as error:
                result['package_verification_error'] = str(error)
        if not preserve:
            try:
                emulator.cleanup()
                result['removed'] = not any(path.exists() for path in (
                    emulator.marker, emulator.workspace / 'avds', emulator.workspace / 'user'))
                if removed.is_file():
                    result['removed_lease'] = json.loads(removed.read_text())
            except Exception as error:
                result['lease_cleanup_error'] = str(error)
        try:
            if log.is_file():
                shutil.copyfile(log, output / f'{role}-emulator.log')
        except OSError as error:
            result['evidence_error'] = str(error)
    return result


def _clean_suite(emulators, profile, output):
    output.mkdir(parents=True, exist_ok=True)
    receipt = output / 'cleanup.json'
    try:
        previous = {entry['role']: entry for entry in json.loads(receipt.read_text())} if receipt.is_file() else {}
    except (OSError, ValueError, KeyError, TypeError):
        previous = {}  # A hard stop can interrupt the receipt before both devices retire.
    outcomes = []
    for role in (profile, 'sender'):
        emulator = emulators[role]
        outcome = previous.get(role)
        remaining = any(path.exists() for path in (
            emulator.marker, emulator.workspace / 'avds', emulator.workspace / 'user'))
        if not outcome or outcome.get('workspace') != str(emulator.workspace) or not outcome['removed'] or remaining:
            outcome = _cleanup_emulator(emulator, role, output)
        outcomes.append(outcome)
    write_json(receipt, outcomes)
    return outcomes


def _cleanup_complete(outcomes):
    return all(row['removed'] and not any(key.endswith('_error') for key in row)
               for row in outcomes)


def cleanup(workspace, sender, output, *, profile='phone', environment=None):
    """Retire this suite's verified disposable emulators after an interrupted run."""
    from build_manager.locking import operation_lock_path, workspace_lock
    from build_manager.retention import linked

    require(profile in MODELS, f'Unknown Android receiver profile: {profile}')
    workspace, output = _suite_workspace(workspace), Path(output)
    marker = workspace / SUITE_MARKER
    with workspace_lock(operation_lock_path(workspace)):
        require(not linked(marker), f'Linked Android suite binding: {marker}')
        if not marker.exists():
            require(not any((workspace / role).exists() for role in ('sender', profile)),
                    f'No Android suite binding for existing emulators under {workspace}')
            write_json(output / 'cleanup.json', [])
            return []
        binding = json.loads(marker.read_text())
        require(binding == dict(profile=profile, sdk=sender['sdk'], sender_sha256=sender['sha256']),
                'Android suite binding differs from the requested cleanup')
        emulators = _suite_emulators(sender, workspace, profile, environment)
        outcomes = _clean_suite(emulators, profile, output)
        require(_cleanup_complete(outcomes), f'Android emulator cleanup incomplete: {output}')
        return outcomes


def run_suite(receiver, sender, workspace, output, *, profile='phone', environment=None):
    """Run all nine cases on one headless, manager-owned sender/receiver pair."""
    from build_manager.locking import operation_lock_path, workspace_lock
    from build_manager.retention import lease
    from logistics_build.build_retention import owned_scratch
    from logistics_build.test_environments import android_image, load

    workspace, output = _suite_workspace(workspace), Path(output).resolve()
    scratch = Path(receiver['workspace']).resolve()
    require(receiver.get('platform') == 'android' and receiver.get('status') == 'built'
            and receiver['identity']['bundle'] == RECEIVER and receiver['identity']['main_module'] == 'logisticsmobile'
            and sender['package'] == SENDER and owned_scratch(scratch), 'Invalid Android acceptance build receipts')
    require(not output.is_relative_to(scratch), 'Retain Android evidence outside the disposable build workspace')
    apks = {package: Path(receipt['apk']).resolve()
            for package, receipt in ((RECEIVER, receiver), (SENDER, sender))}
    hashes = {RECEIVER: receiver['identity']['apk_sha256'], SENDER: sender['sha256']}
    require(all(path.is_relative_to(scratch) for path in apks.values()),
            'Acceptance APKs must be inside the reviewed build workspace')
    image = android_image(load(Path(__file__).resolve().parents[2]))
    emulators = _suite_emulators(sender, workspace, profile, environment)
    driver = Path(__file__).resolve()
    result = dict(status='running', profile=profile, image=image, source=receiver['source'],
                  input_apks={package: dict(path=str(path), sha256=hashes[package]) for package, path in apks.items()},
                  sender=sender, driver=dict(path=str(driver), **digest(driver.read_bytes())), devices={}, cases=[])
    binding = workspace / SUITE_MARKER
    receipt = output / 'result.json'

    with workspace_lock(operation_lock_path(workspace)), lease(scratch):
        require(not workspace.exists() or not any(workspace.iterdir()), f'Expected a fresh workspace: {workspace}')
        require(not receipt.exists() and not (output / 'cleanup.json').exists(),
                f'Expected a new Android evidence directory: {output}')
        for package, path in apks.items():
            with path.open('rb') as stream:
                require(file_digest(stream, 'sha256').hexdigest() == hashes[package],
                        f'APK changed before install: {package}')
        write_json(binding, dict(profile=profile, sdk=sender['sdk'], sender_sha256=sender['sha256']))
        write_json(receipt, result)
        try:
            for role, emulator in emulators.items():
                print(f'Starting owned headless Android {role}', flush=True)
                model = MODELS['phone' if role == 'sender' else profile]
                record = emulator.start(image, model)
                result['devices'][role] = record
                write_json(receipt, result)
                command = record.get('process_started', '').split()
                require('-no-window' in command and '-no-audio' in command,
                        f'Android {role} emulator is missing the headless process arguments')
                _install(emulator, record, apks[SENDER], SENDER, output / role)
            source, target = (result['devices'][role] for role in ('sender', profile))
            emulator = emulators[profile]
            _install(emulator, target, apks[RECEIVER], RECEIVER, output / profile)
            arguments = dict(sender_serial=source['serial'], receiver_serial=target['serial'], adb=emulator.adb,
                             sender_avd=source['name'], receiver_avd=target['name'])
            result['transfer'] = transfer(output=output / 'transfer', **arguments)
            write_json(receipt, result)
            for case in CASES:
                print(f'Running Android {profile} case {case}', flush=True)
                case_output = output / case
                try:
                    outcome = run_case(case, output=case_output, tablet=profile == 'tablet', **arguments)
                except Exception as error:
                    case_receipt = case_output / 'result.json'
                    result['cases'].append(json.loads(case_receipt.read_text()) if case_receipt.is_file()
                                           else dict(case=case, success=False, error=str(error)))
                    raise
                else:
                    result['cases'].append(outcome)
                    write_json(receipt, result)
            result['status'] = 'passed'
        except BaseException as error:
            result.update(status='failed', error=repr(error))
            raise
        finally:
            outcomes = _clean_suite(emulators, profile, output)
            result['cleanup'] = outcomes
            if not _cleanup_complete(outcomes):
                result['status'] = 'failed'
                result['cleanup_error'] = 'Owned Android emulator cleanup is incomplete'
            write_json(receipt, result)
    require(result['status'] == 'passed', f'Android {profile} suite did not complete; see {receipt}')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('build-sender')
    for option in ('workspace', 'sdk', 'java', 'output'):
        build.add_argument('--' + option, type=Path, required=True)
    relay = commands.add_parser('transfer')
    run = commands.add_parser('run-case')
    for command in (relay, run):
        for option in ('sender-serial', 'receiver-serial', 'sender-avd', 'receiver-avd', 'adb', 'output'):
            command.add_argument('--' + option, required=True)
    run.add_argument('case', choices=CASES)
    run.add_argument('--tablet', action='store_true')
    run.add_argument('--launcher')
    args = vars(parser.parse_args())
    command = args.pop('command')
    if command == 'build-sender':
        print(build_sender(**args))
    else:
        operation = transfer if command == 'transfer' else run_case
        print(json.dumps(operation(**args), indent=2))


if __name__ == '__main__':
    main()
