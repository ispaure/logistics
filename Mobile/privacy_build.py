"""Embed the Python provider's OpenSSL privacy declarations before signing."""
from pathlib import Path
import plistlib
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / 'privacy/OpenSSL.xcprivacy'
APP_MANIFEST = ROOT / 'privacy/App.xcprivacy'
MODULES = ('_hashlib', '_ssl')


def verify_manifest(path):
    if not path.is_file():
        raise ValueError('Missing OpenSSL privacy manifest: ' + str(path))
    if plistlib.loads(path.read_bytes()) != plistlib.loads(MANIFEST.read_bytes()):
        raise ValueError('OpenSSL privacy declaration differs from the pinned provider manifest: ' + str(path))


def configure(project):
    framework = Path(project) / 'Support/Python.xcframework'
    script = (framework / 'build/utils.sh').read_text()
    marker = 'mv "$MODULE_PATH/$MODULE_NAME.xcprivacy" "$XCPRIVACY_FILE"'
    if marker not in script or script.index(marker) > script.index('/usr/bin/codesign'):
        raise ValueError('Python support script must embed module privacy manifests before signing.')
    folders = sorted(framework.glob('ios-*/lib*/python*/lib-dynload'))
    if not any('ios-arm64' in p.parts for p in folders):
        raise ValueError('Missing device standard-library extension folder.')
    for folder in folders:
        for module in MODULES:
            if not list(folder.glob(module + '.*.so')):
                raise ValueError('Missing Python OpenSSL extension: ' + str(folder / module))
            destination = folder / (module + '.xcprivacy')
            if not destination.exists():
                shutil.copyfile(MANIFEST, destination)
            verify_manifest(destination)
    configure_app_manifest(Path(project))


def configure_app_manifest(project):
    projects = list(project.glob('*.xcodeproj/project.pbxproj'))
    if len(projects) != 1:
        raise ValueError('Expected one generated Xcode project for the app privacy manifest.')
    path = projects[0]
    try:
        data = plistlib.loads(path.read_bytes())
    except plistlib.InvalidFileException:
        # A newly generated project is OpenStep; older configured projects
        # are XML. Apple's parser accepts both without guessing their syntax.
        data = plistlib.loads(subprocess.check_output(['plutil', '-convert', 'xml1', '-o', '-', str(path)]))
    objects = data['objects']
    groups = [item for item in objects.values() if item.get('isa') == 'PBXGroup' and item.get('path') == 'LogisticsMobile']
    resources = [item for item in objects.values() if item.get('isa') == 'PBXResourcesBuildPhase']
    if len(groups) != 1 or len(resources) != 1:
        raise ValueError('Expected the app resource phase and source group.')
    reference, build = 'A01900000000000000000001', 'A01900000000000000000002'
    entries = {reference: dict(isa='PBXFileReference', lastKnownFileType='text.xml',
                              path='PrivacyInfo.xcprivacy', sourceTree='<group>'),
               build: dict(isa='PBXBuildFile', fileRef=reference)}
    for key, value in entries.items():
        if key in objects and objects[key] != value:
            raise ValueError('App privacy manifest resource identity conflicts with the generated project.')
        objects[key] = value
    if reference not in groups[0]['children']:
        groups[0]['children'].append(reference)
    if build not in resources[0]['files']:
        resources[0]['files'].append(build)
    destination = project / 'LogisticsMobile/PrivacyInfo.xcprivacy'
    destination.parent.mkdir(exist_ok=True)
    shutil.copyfile(APP_MANIFEST, destination)
    path.write_bytes(plistlib.dumps(data, sort_keys=False))


def verify_app(app):
    for module in MODULES:
        verify_manifest(Path(app) / 'Frameworks' / (module + '.framework') / 'PrivacyInfo.xcprivacy')
    path = Path(app) / 'PrivacyInfo.xcprivacy'
    if not path.is_file() or plistlib.loads(path.read_bytes()) != plistlib.loads(APP_MANIFEST.read_bytes()):
        raise ValueError('Missing or incorrect app privacy manifest: ' + str(path))
