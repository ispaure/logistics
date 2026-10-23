"""Build and link the pinned read-only rclone bridge into generated native apps."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shlex
import shutil
import subprocess
import tomllib

try:
    from .build_support.icon_build import configure_android as configure_android_icons, configure_ios as configure_ios_icons
    from .build_support.scene_build import configure as configure_scene
    from .build_support.privacy_build import configure as configure_privacy
    from .build_support.camera_build import configure as configure_camera
    from .deployment_paths import output_root
except ImportError:
    from build_support.icon_build import configure_android as configure_android_icons, configure_ios as configure_ios_icons
    from build_support.scene_build import configure as configure_scene
    from build_support.privacy_build import configure as configure_privacy
    from build_support.camera_build import configure as configure_camera
    from deployment_paths import output_root

ROOT = Path(__file__).resolve().parent
FLAGS = '-s -w -X github.com/rclone/rclone/fs.Version=v1.74.1'


def ios_compiler(target, sdk_path):
    # Go parses CC into arguments; the SDK may live in "Xcode 27.1.app".
    return shlex.join(['clang', '-target', target, '-isysroot', sdk_path])


def run(*args, env=None, cwd=ROOT / 'rclone_bridge'):
    subprocess.run(args, check=True, env=env, cwd=cwd)


def configure_android_sources(project):
    """Refresh native source roots even when Briefcase reuses an older project."""
    config = tomllib.loads((ROOT / 'pyproject.toml').read_text())
    android = config['tool']['briefcase']['app']['logisticsmobile']['android']
    gradle = Path(project) / 'app/build.gradle'
    text = gradle.read_text()
    # Briefcase update retains the generated project's original version code.
    # Keep in-place device updates aligned with the current source manifest.
    text, count = re.subn(r'(?m)^([ \t]*versionCode[ \t]+)\d+[ \t]*$',
                         lambda match: match[1] + str(android['version_code']), text)
    if count != 1:
        raise ValueError('Expected one Android versionCode in generated build.gradle.')
    for line in android['build_gradle_extra_content'].splitlines():
        if line.startswith('android.sourceSets.main.java.srcDir(') and line not in text.splitlines():
            text += '\n' + line + '\n'
    gradle.write_text(text)
    # Media custom actions need resource IDs, including Android 13+ lock screens.
    import shutil
    resources = ROOT.parent / 'Python/features/books/mobile/android_res'
    shutil.copytree(resources, Path(project) / 'app/src/main/res', dirs_exist_ok=True)
    shutil.copytree(ROOT.parent / 'Python/mobile/android_res',
                    Path(project) / 'app/src/main/res', dirs_exist_ok=True)
    # Firebase builds invoke Gradle directly, so Briefcase's build-time metadata
    # hook has not run in a fresh checkout (and may retain test mode in an old one).
    metadata = Path(project) / 'app/src/main/res/values/briefcase.xml'
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text('<resources><string name="main_module">logisticsmobile</string></resources>\n')
    (Path(project) / 'app/extract-packages.txt').write_text('')



def configure_android_appearance(project):
    """Use DayNight resources and preserve Python sessions across uiMode changes."""
    import xml.etree.ElementTree as ET
    project = Path(project)
    styles = project / 'app/src/main/res/values/styles.xml'
    text = styles.read_text()
    text = text.replace('Theme.AppCompat.Light.DarkActionBar', 'Theme.MaterialComponents.DayNight')
    styles.write_text(text)
    manifest = project / 'app/src/main/AndroidManifest.xml'
    namespace = 'http://schemas.android.com/apk/res/android'
    ET.register_namespace('android', namespace)
    tree = ET.parse(manifest)
    for activity in tree.getroot().findall('application/activity'):
        key = '{' + namespace + '}configChanges'
        flags = activity.get(key, '').split('|')
        if 'uiMode' not in flags:
            activity.set(key, '|'.join([flag for flag in flags if flag] + ['uiMode']))
    root = tree.getroot()
    permission = 'android.permission.MANAGE_EXTERNAL_STORAGE'
    if not any(item.get('{' + namespace + '}name') == permission for item in root.findall('uses-permission')):
        ET.SubElement(root, 'uses-permission', {'{' + namespace + '}name': permission})
    for permission in ('android.permission.FOREGROUND_SERVICE', 'android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK',
                       'android.permission.WAKE_LOCK'):
        if not any(item.get('{' + namespace + '}name') == permission for item in root.findall('uses-permission')):
            ET.SubElement(root, 'uses-permission', {'{' + namespace + '}name': permission})
    application = root.find('application')
    service = 'io.github.ispaure.logistics.books.SpeechMediaService'
    if not any(item.get('{' + namespace + '}name') == service for item in application.findall('service')):
        ET.SubElement(application, 'service', {'{' + namespace + '}name': service,
            '{' + namespace + '}exported': 'false', '{' + namespace + '}foregroundServiceType': 'mediaPlayback'})
    speech_queries = ET.parse(ROOT.parent / 'Python/features/books/mobile/android_speech_queries.xml').getroot()
    query = root.find('queries')
    if query is None:
        root.append(speech_queries)
    elif not any(action.get('{' + namespace + '}name') == 'android.intent.action.TTS_SERVICE'
                 for action in query.findall('intent/action')):
        query.append(speech_queries.find('intent'))
    tree.write(manifest, encoding='utf-8', xml_declaration=True)


def android():
    sdk = Path(os.environ.get('ANDROID_HOME') or os.environ['ANDROID_SDK_ROOT'])
    ndk = sdk / 'ndk' / '27.2.12479018'
    if not ndk.is_dir():
        managers = [sdk / 'cmdline-tools/latest/bin/sdkmanager', *sorted(sdk.glob('cmdline-tools/*/bin/sdkmanager'), reverse=True)]
        manager = next((path for path in managers if path.is_file()), None)
        if manager is None:
            raise ValueError('Android SDK command-line tools are required to install the NDK.')
        run(str(manager), 'ndk;27.2.12479018')
    host = 'linux-x86_64' if platform.system() == 'Linux' else 'darwin-x86_64'
    tools = ndk / 'toolchains/llvm/prebuilt' / host / 'bin'
    project = output_root(ROOT) / 'build/logisticsmobile/android/gradle'
    configure_android_sources(project)
    configure_android_appearance(project)
    configure_android_icons(project)
    for arch, abi, compiler in [('arm64', 'arm64-v8a', 'aarch64-linux-android24-clang'),
                                 ('amd64', 'x86_64', 'x86_64-linux-android24-clang')]:
        destination = project / 'app/src/main/jniLibs' / abi
        destination.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, CGO_ENABLED='1', GOOS='android', GOARCH=arch, CC=str(tools / compiler),
                   CGO_LDFLAGS='-Wl,-z,max-page-size=16384')
        run('go', 'build', '-trimpath', '-ldflags=' + FLAGS, '-buildmode=c-shared',
            '-o', str(destination / 'liblogisticscloud.so'), '.', env=env)
        headers = subprocess.check_output([str(tools / 'llvm-readelf'), '-l', '--wide',
                                            str(destination / 'liblogisticscloud.so')], text=True)
        loads = [line.split() for line in headers.splitlines() if line.strip().startswith('LOAD ')]
        if not loads or any(int(row[-1], 16) < 16384 for row in loads):
            raise ValueError('The Android rclone library is missing 16 KiB ELF load alignment.')
        (destination / 'liblogisticscloud.h').unlink()


def ios(project=None):
    project = Path(project) if project is not None else output_root(ROOT) / 'build/logisticsmobile/ios/xcode'
    configure_ios_icons(project)
    configure_scene(project)
    configure_privacy(project)
    configure_camera(project)
    support = project / 'Support'
    support.mkdir(parents=True, exist_ok=True)
    arch = {'arm64': 'arm64', 'aarch64': 'arm64', 'x86_64': 'amd64'}[platform.machine()]
    for sdk, variant, go_arch, target in [
        ('iphonesimulator', 'simulator', arch, ('arm64' if arch == 'arm64' else 'x86_64') + '-apple-ios15.0-simulator'),
        ('iphoneos', 'device', 'arm64', 'arm64-apple-ios15.0')]:
        path = subprocess.check_output(['xcrun', '--sdk', sdk, '--show-sdk-path'], text=True).strip()
        env = dict(os.environ, CGO_ENABLED='1', GOOS='ios', GOARCH=go_arch,
                   CC=ios_compiler(target, path))
        run('go', 'build', '-trimpath', '-ldflags=' + FLAGS, '-buildmode=c-archive',
            '-o', str(support / f'liblogisticscloud-{variant}.a'), '.', env=env)
    pbx = project / 'Logistics Mobile.xcodeproj/project.pbxproj'
    data = json.loads(subprocess.check_output(['plutil', '-convert', 'json', '-o', '-', str(pbx)]))
    found = 0
    for obj in data['objects'].values():
        if obj.get('isa') != 'XCBuildConfiguration' or 'PRODUCT_BUNDLE_IDENTIFIER' not in obj.get('buildSettings', {}):
            continue
        found += 1
        settings = obj['buildSettings']
        for sdk, variant in [('iphonesimulator', 'simulator'), ('iphoneos', 'device')]:
            settings[f'OTHER_LDFLAGS[sdk={sdk}*]'] = ['$(inherited)',
                f'-Wl,-force_load,$(SRCROOT)/Support/liblogisticscloud-{variant}.a',
                '-Wl,-u,_LogisticsCloud', '-Wl,-u,_LogisticsCloudFree', '-Wl,-export_dynamic',
                '-framework', 'CoreFoundation', '-framework', 'Security',
                '-framework', 'AVFoundation', '-framework', 'Photos', '-lresolv']
    if found != 2:
        raise ValueError('Unexpected Briefcase iOS build configuration; refusing to silently omit the bridge.')
    pbx.write_bytes(plistlib.dumps(data, sort_keys=False))


def licenses(destination=None):
    """Carry notices for the modules actually compiled into the native engine."""
    raw = subprocess.check_output(['go', 'list', '-deps', '-json', '.'], cwd=ROOT / 'rclone_bridge', text=True)
    decoder, modules = json.JSONDecoder(), {}
    while raw.strip():
        value, end = decoder.raw_decode(raw.lstrip())
        raw = raw.lstrip()[end:]
        module = value.get('Module', {})
        if module.get('Version'):
            modules[module['Path']] = module
    destination = Path(destination) if destination is not None else output_root(ROOT) / 'payload/mobile/native-licenses'
    destination.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, module in sorted(modules.items()):
        root = Path(module['Dir'])
        files = [p for p in root.iterdir() if p.is_file()
                 and p.name.upper().startswith(('LICENSE', 'COPYING', 'NOTICE'))]
        if not files:
            raise ValueError('No license notice found for native dependency: ' + name)
        records = []
        for source in files:
            if source.stat().st_size > 512 * 1024:
                raise ValueError('Unexpected native dependency notice size.')
            target = destination / (name.replace('/', '_') + '-' + module['Version'] + '-' + source.name)
            shutil.copyfile(source, target)
            records.append(dict(file=target.name, sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
        manifest.append(dict(module=name, version=module['Version'], notices=records))
    goroot = Path(subprocess.check_output(['go', 'env', 'GOROOT'], text=True).strip())
    shutil.copyfile(goroot / 'LICENSE', destination / 'Go-LICENSE')
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', choices=['android', 'ios', 'host', 'licenses'])
    args = parser.parse_args()
    if not shutil.which('go'):
        parser.error('Install the pinned Go 1.26.9 toolchain first.')
    if args.target == 'licenses':
        licenses()
        return
    run('go', 'test', './...')
    if args.target == 'android':
        android()
    elif args.target == 'ios':
        ios()
    else:
        destination = ROOT / 'build/cloud-host'
        destination.mkdir(parents=True, exist_ok=True)
        run('go', 'build', '-buildmode=c-shared', '-o', str(destination / 'liblogisticscloud.dylib'), '.')


if __name__ == '__main__':
    main()
