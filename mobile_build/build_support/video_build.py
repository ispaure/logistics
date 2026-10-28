"""Install feature-owned native video adapters into managed mobile builds."""
from hashlib import sha256
from pathlib import Path
import plistlib
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
VLC_REVISION = '2e0868f5ed40fe59cd92f377645fdcc260c6e759'


def configure_android(project):
    path = Path(project) / 'app/src/main/AndroidManifest.xml'
    namespace = 'http://schemas.android.com/apk/res/android'
    ET.register_namespace('android', namespace)
    def attr(name):
        return '{' + namespace + '}' + name
    tree = ET.parse(path)
    application = tree.getroot().find('application')
    for activity in application.findall('activity'):
        if any(category.get(attr('name')) == 'android.intent.category.LAUNCHER'
               for category in activity.findall('intent-filter/category')):
            activity.set(attr('supportsPictureInPicture'), 'true')
            flags = activity.get(attr('configChanges'), '').split('|')
            activity.set(attr('configChanges'), '|'.join(dict.fromkeys(
                [flag for flag in flags if flag] + ['screenSize', 'smallestScreenSize', 'screenLayout', 'orientation'])))
    tree.write(path, encoding='utf-8', xml_declaration=True)


def configure_ios(project):
    project = Path(project)
    source = ROOT / 'Python/features/video/mobile/ios/VideoPlayer.m'
    support = project / 'Support'
    support.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, support / 'VideoPlayer.m')
    launcher = project / 'LogisticsMobile/main.m'
    text = launcher.read_text()
    include = '#import "../Support/VideoPlayer.m"'
    if include not in text:
        launcher.write_text(text.replace('#import <UIKit/UIKit.h>', '#import <UIKit/UIKit.h>\n' + include))
    pbx = next(project.glob('*.xcodeproj/project.pbxproj'))
    try:
        data = plistlib.loads(pbx.read_bytes())
    except plistlib.InvalidFileException:
        data = plistlib.loads(subprocess.check_output(['plutil', '-convert', 'xml1', '-o', '-', str(pbx)]))
    objects = data['objects']
    targets = [obj for obj in objects.values() if obj.get('productType') == 'com.apple.product-type.application']
    if len(targets) != 1:
        raise ValueError('Expected one containing iOS video app.')
    target = targets[0]
    def put(name, **value):
        key = sha256(('logistics.video.' + name).encode()).hexdigest()[:24].upper()
        objects[key] = value
        return key
    package = put('package', isa='XCRemoteSwiftPackageReference',
        repositoryURL='https://github.com/videolan/vlckit.git',
        requirement=dict(kind='revision', revision=VLC_REVISION))
    product = put('product', isa='XCSwiftPackageProductDependency', package=package, productName='VLCKit')
    build_file = put('framework', isa='PBXBuildFile', productRef=product)
    project_object = objects[data['rootObject']]
    packages = project_object.setdefault('packageReferences', [])
    if package not in packages:
        packages.append(package)
    dependencies = target.setdefault('packageProductDependencies', [])
    if product not in dependencies:
        dependencies.append(product)
    phase = next((objects[key] for key in target['buildPhases']
                  if objects[key]['isa'] == 'PBXFrameworksBuildPhase'), None)
    if phase is None:
        raise ValueError('Missing iOS framework link phase.')
    if build_file not in phase['files']:
        phase['files'].append(build_file)
    callkit = put('callkit-reference', isa='PBXFileReference', lastKnownFileType='wrapper.framework',
        path='System/Library/Frameworks/CallKit.framework', sourceTree='SDKROOT')
    callkit_build = put('callkit-build', isa='PBXBuildFile', fileRef=callkit)
    if callkit_build not in phase['files']:
        phase['files'].append(callkit_build)
    pbx.write_bytes(plistlib.dumps(data, sort_keys=False))
    info = project / 'LogisticsMobile/LogisticsMobile-Info.plist'
    metadata = plistlib.loads(info.read_bytes())
    # VLC's Chromecast discoverer uses mDNS, guarded by local-network permission.
    bonjour = metadata.setdefault('NSBonjourServices', [])
    for service in ('_googlecast._tcp',):
        if service not in bonjour:
            bonjour.append(service)
    info.write_bytes(plistlib.dumps(metadata, sort_keys=False))
