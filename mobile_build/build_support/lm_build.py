"""Compile the feature-owned Foundation Models bridge in the main app target."""
from hashlib import sha256
from pathlib import Path
import plistlib
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


def configure_ios(project):
    project = Path(project)
    support = project / 'Support'
    support.mkdir(exist_ok=True)
    shutil.copyfile(ROOT / 'Python/features/lm/mobile/ios/FoundationChat.swift', support / 'FoundationChat.swift')
    pbx = next(project.glob('*.xcodeproj/project.pbxproj'))
    try:
        data = plistlib.loads(pbx.read_bytes())
    except plistlib.InvalidFileException:
        data = plistlib.loads(subprocess.check_output(['plutil', '-convert', 'xml1', '-o', '-', str(pbx)]))
    objects = data['objects']
    targets = [obj for obj in objects.values() if obj.get('productType') == 'com.apple.product-type.application' and obj.get('name') != 'LogisticsWatch']
    if len(targets) != 1:
        raise ValueError('Expected one main application for on-device chat.')
    target = targets[0]
    def put(name, **value):
        key = sha256(('logistics.lm.' + name).encode()).hexdigest()[:24].upper()
        objects[key] = value
        return key
    reference = put('source', isa='PBXFileReference', lastKnownFileType='sourcecode.swift',
                    path='Support/FoundationChat.swift', sourceTree='SOURCE_ROOT')
    build = put('build', isa='PBXBuildFile', fileRef=reference)
    group = objects[objects[data['rootObject']]['mainGroup']]['children']
    if reference not in group:
        group.append(reference)
    phase = next(objects[key] for key in target['buildPhases'] if objects[key]['isa'] == 'PBXSourcesBuildPhase')
    if build not in phase['files']:
        phase['files'].append(build)
    for key in objects[target['buildConfigurationList']]['buildConfigurations']:
        settings = objects[key]['buildSettings']
        flags = settings.get('OTHER_LDFLAGS', ['$(inherited)'])
        if isinstance(flags, str):
            import shlex
            flags = shlex.split(flags)
        if 'FoundationModels' not in flags:
            flags.extend(['-weak_framework', 'FoundationModels'])
        settings['OTHER_LDFLAGS'] = flags
        settings['SWIFT_VERSION'] = '5.0'
        settings['ALWAYS_EMBED_SWIFT_STANDARD_LIBRARIES'] = 'YES'
    pbx.write_bytes(plistlib.dumps(data, sort_keys=False))


def configure_android(project):
    # These two optional libraries declare API 26 but have no startup components.
    # Keep the host's API 24 support; NanoBridge gates all ML Kit loads on API 26.
    path = Path(project) / 'app/src/main/AndroidManifest.xml'
    tools = 'http://schemas.android.com/tools'
    ET.register_namespace('android', 'http://schemas.android.com/apk/res/android')
    ET.register_namespace('tools', tools)
    tree = ET.parse(path)
    sdk = tree.getroot().find('uses-sdk')
    if sdk is None:
        sdk = ET.SubElement(tree.getroot(), 'uses-sdk')
    key = '{' + tools + '}overrideLibrary'
    libraries = [value.strip() for value in sdk.get(key, '').split(',') if value.strip()]
    for library in ('com.google.mlkit.genai.prompt', 'com.google.mlkit.genai.common'):
        if library not in libraries:
            libraries.append(library)
    sdk.set(key, ','.join(libraries))
    tree.write(path, encoding='utf-8', xml_declaration=True)
