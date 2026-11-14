"""Install feature-owned native video adapters into managed mobile builds."""
from hashlib import sha256
from pathlib import Path
import plistlib
import shutil
import subprocess
import tarfile
import xml.etree.ElementTree as ET
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
VLC_REVISION = '2e0868f5ed40fe59cd92f377645fdcc260c6e759'
FFMPEG_HEADERS_URL = 'https://ffmpeg.org/releases/ffmpeg-9.0.tar.xz'
FFMPEG_HEADERS_SHA256 = '7f607a00dd0d28a729d5a4811205812eef01cf6ef6155025febb6f36a9062d52'


def install_remux_headers(support):
    """Stage public headers for the FFmpeg 9.0 ABI already linked in VLCKit."""
    from io import BytesIO

    with urlopen(FFMPEG_HEADERS_URL, timeout=45) as response:
        archive = response.read(16 * 1024 * 1024)
    if sha256(archive).hexdigest() != FFMPEG_HEADERS_SHA256:
        raise ValueError('FFmpeg headers archive checksum mismatch.')
    destination = Path(support) / 'VideoFFmpeg'
    with tarfile.open(fileobj=BytesIO(archive), mode='r:xz') as package:
        for member in package:
            parts = Path(member.name).parts
            if (len(parts) == 3 and parts[1] in {'libavformat', 'libavcodec', 'libavutil'}
                    and member.isfile() and parts[2].endswith('.h')):
                header = destination.joinpath(*parts[1:])
                header.parent.mkdir(parents=True, exist_ok=True)
                header.write_bytes(package.extractfile(member).read())
    (destination / 'libavutil/avconfig.h').write_text(
        '#pragma once\n#define AV_HAVE_BIGENDIAN 0\n#define AV_HAVE_FAST_UNALIGNED 1\n')


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


def configure_ios(project, *, remux_headers=None):
    project = Path(project)
    source = ROOT / 'Python/features/video/mobile/ios/VideoPlayer.m'
    support = project / 'Support'
    support.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, support / 'VideoPlayer.m')
    shutil.copyfile(ROOT / 'Python/mobile/ios/ScreenAwake.m', support / 'ScreenAwake.m')
    for helper in source.parent.glob('*.m'):
        shutil.copyfile(helper, support / helper.name)
    if remux_headers is not None:
        shutil.copytree(remux_headers, support / 'VideoFFmpeg', dirs_exist_ok=True)
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
    targets = [obj for obj in objects.values() if obj.get('productType') == 'com.apple.product-type.application' and obj.get('name') != 'LogisticsWatch']
    if len(targets) != 1:
        raise ValueError('Expected one containing iOS video app.')
    target = targets[0]
    if remux_headers is not None:
        for key in objects[target['buildConfigurationList']]['buildConfigurations']:
            settings = objects[key]['buildSettings']
            paths = settings.setdefault('HEADER_SEARCH_PATHS', ['$(inherited)'])
            if isinstance(paths, str):
                paths = settings['HEADER_SEARCH_PATHS'] = [paths]
            path = '$(SRCROOT)/Support/VideoFFmpeg'
            if path not in paths:
                paths.append(path)
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
    for name in ('AVKit', 'CoreImage'):
        reference = put(name + '-reference', isa='PBXFileReference', lastKnownFileType='wrapper.framework',
            path='System/Library/Frameworks/' + name + '.framework', sourceTree='SDKROOT')
        linked = put(name + '-build', isa='PBXBuildFile', fileRef=reference)
        if linked not in phase['files']:
            phase['files'].append(linked)
    pbx.write_bytes(plistlib.dumps(data, sort_keys=False))
    info = project / 'LogisticsMobile/LogisticsMobile-Info.plist'
    metadata = plistlib.loads(info.read_bytes())
    metadata.setdefault('NSAppTransportSecurity', {})['NSAllowsLocalNetworking'] = True
    # VLC's Chromecast discoverer uses mDNS, guarded by local-network permission.
    bonjour = metadata.setdefault('NSBonjourServices', [])
    for service in ('_googlecast._tcp',):
        if service not in bonjour:
            bonjour.append(service)
    info.write_bytes(plistlib.dumps(metadata, sort_keys=False))
