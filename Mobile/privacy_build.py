"""Embed the Python provider's OpenSSL privacy declarations before signing."""
from pathlib import Path
import plistlib
import shutil

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / 'privacy/OpenSSL.xcprivacy'
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


def verify_app(app):
    for module in MODULES:
        verify_manifest(Path(app) / 'Frameworks' / (module + '.framework') / 'PrivacyInfo.xcprivacy')
