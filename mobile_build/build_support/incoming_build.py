"""Install native incoming-file targets into canonical generated projects."""
from hashlib import sha256
from pathlib import Path
import plistlib
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
GROUP = 'group.io.github.ispaure.logisticsmobile'
ACTIVITY = 'io.github.ispaure.logisticsmobile.ReceiveActivity'


def configure_android(project):
    path = Path(project) / 'app/src/main/AndroidManifest.xml'
    namespace = 'http://schemas.android.com/apk/res/android'
    ET.register_namespace('android', namespace)
    attr = lambda name: '{' + namespace + '}' + name
    tree = ET.parse(path)
    application = tree.getroot().find('application')
    activity = next((a for a in application.findall('activity') if a.get(attr('name')) == ACTIVITY), None)
    if activity is None:
        activity = ET.SubElement(application, 'activity')
    activity.attrib.update({attr('name'): ACTIVITY, attr('exported'): 'true',
        attr('label'): 'Logisticks', attr('configChanges'): 'orientation|screenSize|keyboardHidden|uiMode',
        attr('excludeFromRecents'): 'true'})
    for old in list(activity):
        activity.remove(old)
    for action in ('SEND', 'SEND_MULTIPLE'):
        intent = ET.SubElement(activity, 'intent-filter')
        ET.SubElement(intent, 'action', {attr('name'): 'android.intent.action.' + action})
        ET.SubElement(intent, 'category', {attr('name'): 'android.intent.category.DEFAULT'})
        ET.SubElement(intent, 'data', {attr('mimeType'): '*/*'})
    tree.write(path, encoding='utf-8', xml_declaration=True)


def _key(name):
    return sha256(('logistics.incoming.' + name).encode()).hexdigest()[:24].upper()


def configure_ios(project):
    project = Path(project)
    pbx = next(project.glob('*.xcodeproj/project.pbxproj'))
    try:
        data = plistlib.loads(pbx.read_bytes())
    except plistlib.InvalidFileException:
        data = plistlib.loads(subprocess.check_output(['plutil', '-convert', 'xml1', '-o', '-', str(pbx)]))
    objects = data['objects']
    targets = [(key, obj) for key, obj in objects.items() if obj.get('productType') == 'com.apple.product-type.application' and obj.get('name') != 'LogisticsWatch']
    if len(targets) != 1:
        raise ValueError('Expected one containing app for the share extension.')
    app_id, app = targets[0]
    app_configs = objects[app['buildConfigurationList']]['buildConfigurations']
    settings = [objects[key]['buildSettings'] for key in app_configs]
    bundle_ids = {s['PRODUCT_BUNDLE_IDENTIFIER'] for s in settings}
    if len(bundle_ids) != 1:
        raise ValueError('Containing app bundle identities differ.')
    bundle = bundle_ids.pop()
    destination = project / 'IncomingShare'
    destination.mkdir(exist_ok=True)
    for name in ('IncomingFiles.m', 'ShareViewController.m'):
        shutil.copyfile(ROOT / 'Python/mobile/ios' / name, destination / name)
    # The main scene callbacks call the same bounded native receiver for Open in.
    launcher = project / 'LogisticsMobile/main.m'
    text = launcher.read_text()
    include = '#import "../IncomingShare/IncomingFiles.m"'
    if include not in text:
        launcher.write_text(text.replace('#import <UIKit/UIKit.h>', '#import <UIKit/UIKit.h>\n' + include))
    info = project / 'LogisticsMobile/LogisticsMobile-Info.plist'
    metadata = plistlib.loads(info.read_bytes())
    metadata['CFBundleDocumentTypes'] = [dict(CFBundleTypeName='Files', CFBundleTypeRole='Viewer',
        LSHandlerRank='Alternate', LSItemContentTypes=['public.data', 'public.content'])]
    metadata['LSSupportsOpeningDocumentsInPlace'] = True
    info.write_bytes(plistlib.dumps(metadata))
    for config in settings:
        relative = config.get('CODE_SIGN_ENTITLEMENTS', 'IncomingShare/Main.entitlements')
        if '$' in relative or Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise ValueError('Unexpected containing app entitlement path.')
        path = project / relative
        entitlements = plistlib.loads(path.read_bytes()) if path.exists() else {}
        groups = entitlements.setdefault('com.apple.security.application-groups', [])
        if GROUP not in groups:
            groups.append(GROUP)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(plistlib.dumps(entitlements))
        config['CODE_SIGN_ENTITLEMENTS'] = relative
    (destination / 'Share.entitlements').write_bytes(plistlib.dumps({'com.apple.security.application-groups':[GROUP]}))
    (destination / 'Info.plist').write_bytes(plistlib.dumps(dict(
        CFBundleDisplayName='Logisticks', CFBundleName='Logisticks Inbox',
        CFBundleExecutable='$(EXECUTABLE_NAME)', CFBundleIdentifier='$(PRODUCT_BUNDLE_IDENTIFIER)',
        CFBundlePackageType='XPC!', CFBundleShortVersionString='$(MARKETING_VERSION)',
        CFBundleVersion='$(CURRENT_PROJECT_VERSION)',
        NSExtension=dict(NSExtensionPointIdentifier='com.apple.share-services',
            NSExtensionPrincipalClass='LogisticsShareViewController',
            NSExtensionAttributes=dict(NSExtensionActivationRule={
                'NSExtensionActivationSupportsFileWithMaxCount':100,
                'NSExtensionActivationSupportsImageWithMaxCount':100,
                'NSExtensionActivationSupportsMovieWithMaxCount':100})))) )
    def put(identity, **value):
        key = _key(identity)
        objects[key] = value
        return key
    reference = put('source', isa='PBXFileReference', lastKnownFileType='sourcecode.c.objc',
        path='IncomingShare/ShareViewController.m', sourceTree='SOURCE_ROOT')
    product = put('product', isa='PBXFileReference', explicitFileType='wrapper.app-extension',
        path='LogisticsInbox.appex', sourceTree='BUILT_PRODUCTS_DIR', includeInIndex='0')
    source_build = put('source build', isa='PBXBuildFile', fileRef=reference)
    sources = put('sources', isa='PBXSourcesBuildPhase', buildActionMask='2147483647',
        files=[source_build], runOnlyForDeploymentPostprocessing='0')
    frameworks = put('frameworks', isa='PBXFrameworksBuildPhase', buildActionMask='2147483647',
        files=[], runOnlyForDeploymentPostprocessing='0')
    configurations = []
    for key in app_configs:
        original = objects[key]
        base = original['buildSettings']
        build = dict(PRODUCT_BUNDLE_IDENTIFIER=bundle + '.inbox', PRODUCT_NAME='LogisticsInbox',
            INFOPLIST_FILE='IncomingShare/Info.plist', CODE_SIGN_ENTITLEMENTS='IncomingShare/Share.entitlements',
            CLANG_ENABLE_OBJC_ARC='YES', APPLICATION_EXTENSION_API_ONLY='YES', SKIP_INSTALL='YES',
            IPHONEOS_DEPLOYMENT_TARGET='15.0', TARGETED_DEVICE_FAMILY='1,2', SDKROOT='iphoneos',
            LD_RUNPATH_SEARCH_PATHS=['$(inherited)', '@executable_path/Frameworks', '@executable_path/../../Frameworks'],
            OTHER_LDFLAGS=['-framework', 'UIKit', '-framework', 'UniformTypeIdentifiers'],
            MARKETING_VERSION=str(metadata['CFBundleShortVersionString']),
            CURRENT_PROJECT_VERSION=str(metadata['CFBundleVersion']))
        for name in ('DEVELOPMENT_TEAM', 'CODE_SIGN_STYLE', 'CODE_SIGN_IDENTITY'):
            if name in base:
                build[name] = base[name]
        configurations.append(put('config ' + original['name'], isa='XCBuildConfiguration',
                                  name=original['name'], buildSettings=build))
    config_list = put('configuration list', isa='XCConfigurationList', buildConfigurations=configurations,
                      defaultConfigurationIsVisible='0', defaultConfigurationName='Release')
    target = put('target', isa='PBXNativeTarget', name='Logistics Inbox', productName='LogisticsInbox',
        productReference=product, productType='com.apple.product-type.app-extension',
        buildConfigurationList=config_list, buildPhases=[sources, frameworks], buildRules=[], dependencies=[])
    proxy = put('proxy', isa='PBXContainerItemProxy', containerPortal=data['rootObject'],
        proxyType='1', remoteGlobalIDString=target, remoteInfo='Logistics Inbox')
    dependency = put('dependency', isa='PBXTargetDependency', target=target, targetProxy=proxy)
    embed_file = put('embed file', isa='PBXBuildFile', fileRef=product,
        settings={'ATTRIBUTES':['RemoveHeadersOnCopy']})
    embed = put('embed', isa='PBXCopyFilesBuildPhase', buildActionMask='2147483647',
        dstPath='', dstSubfolderSpec='13', name='Embed App Extensions', files=[embed_file],
        runOnlyForDeploymentPostprocessing='0')
    project_object = objects[data['rootObject']]
    def append_unique(values, value):
        if value not in values:
            values.append(value)
    append_unique(project_object['targets'], target)
    append_unique(app['dependencies'], dependency)
    append_unique(app['buildPhases'], embed)
    append_unique(objects[project_object['mainGroup']]['children'], reference)
    append_unique(objects[project_object['productRefGroup']]['children'], product)
    for key in (app_id, target):
        attributes = project_object.setdefault('attributes', {}).setdefault('TargetAttributes', {}).setdefault(key, {})
        attributes.setdefault('SystemCapabilities', {})['com.apple.ApplicationGroups.iOS'] = {'enabled':1}
    pbx.write_bytes(plistlib.dumps(data, sort_keys=False))
