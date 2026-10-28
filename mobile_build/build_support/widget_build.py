"""Embed lightweight widget/Shortcuts extensions without the Python app runtime."""
from hashlib import sha256
from pathlib import Path
import plistlib
import shutil
import subprocess

from .incoming_build import GROUP

ROOT = Path(__file__).resolve().parents[2]
EXTENSIONS = (
    ('LogisticsWidget', '.widgets', 'com.apple.widgetkit-extension',
     ('WidgetSettings.swift', 'ValueWidget.swift'), ('WidgetValueStore.swift', 'WidgetValueView.swift')),
    ('LogisticsWidgetActions', '.widget-actions', 'com.apple.appintents-extension',
     ('WidgetSettings.swift', 'SetWidgetValue.swift'), ('WidgetValueStore.swift',)),
)


def configure_ios(project):
    project = Path(project)
    pbx = next(project.glob('*.xcodeproj/project.pbxproj'))
    try:
        data = plistlib.loads(pbx.read_bytes())
    except plistlib.InvalidFileException:
        data = plistlib.loads(subprocess.check_output(['plutil', '-convert', 'xml1', '-o', '-', str(pbx)]))
    objects = data['objects']
    apps = [(key, value) for key, value in objects.items()
            if value.get('productType') == 'com.apple.product-type.application']
    if len(apps) != 1:
        raise ValueError('Expected one containing app for widgets.')
    app_id, app = apps[0]
    configs = [objects[key] for key in objects[app['buildConfigurationList']]['buildConfigurations']]
    bundles = {config['buildSettings']['PRODUCT_BUNDLE_IDENTIFIER'] for config in configs}
    if len(bundles) != 1:
        raise ValueError('Containing app bundle identities differ.')
    bundle = bundles.pop()
    metadata = plistlib.loads((project / 'LogisticsMobile/LogisticsMobile-Info.plist').read_bytes())
    project_object = objects[data['rootObject']]

    def append_unique(values, value):
        if value not in values:
            values.append(value)

    def put(identity, **values):
        key = sha256(('logistics.widget.' + identity).encode()).hexdigest()[:24].upper()
        objects[key] = values
        return key

    # Share the existing app group; never replace other capabilities or app identity.
    for config in configs:
        settings = config['buildSettings']
        relative = settings.get('CODE_SIGN_ENTITLEMENTS')
        if not relative or '$' in relative or Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise ValueError('Expected an owned containing-app entitlement file for widgets.')
        path = project / relative
        entitlements = plistlib.loads(path.read_bytes())
        append_unique(entitlements.setdefault('com.apple.security.application-groups', []), GROUP)
        path.write_bytes(plistlib.dumps(entitlements))

    for product_name, suffix, extension_point, local_sources, shared_sources in EXTENSIONS:
        extension_kit = suffix == '.widget-actions'
        destination = project / product_name
        destination.mkdir(exist_ok=True)
        for name in local_sources:
            shutil.copyfile(ROOT / 'Python/mobile/ios/widgets' / name, destination / name)
        for name in shared_sources:
            shutil.copyfile(ROOT / 'Python/commonUtils/ui/native/ios' / name, destination / name)
        (destination / 'Extension.entitlements').write_bytes(plistlib.dumps({
            'com.apple.security.application-groups': [GROUP]}))
        extension_metadata = dict(EXAppExtensionAttributes=dict(EXExtensionPointIdentifier=extension_point)) if extension_kit else dict(
            NSExtension=dict(NSExtensionPointIdentifier=extension_point))
        (destination / 'Info.plist').write_bytes(plistlib.dumps(dict(
            CFBundleDisplayName='Logistics', CFBundleName=product_name,
            CFBundleExecutable='$(EXECUTABLE_NAME)', CFBundleIdentifier='$(PRODUCT_BUNDLE_IDENTIFIER)',
            CFBundlePackageType='XPC!',
            CFBundleShortVersionString=str(metadata['CFBundleShortVersionString']),
            CFBundleVersion=str(metadata['CFBundleVersion']), **extension_metadata)))
        prefix = product_name + ' '
        source_builds = []
        for name in (*local_sources, *shared_sources):
            reference = put(prefix + name, isa='PBXFileReference', lastKnownFileType='sourcecode.swift',
                            path=product_name + '/' + name, sourceTree='SOURCE_ROOT')
            source_builds.append(put(prefix + name + ' build', isa='PBXBuildFile', fileRef=reference))
            append_unique(objects[project_object['mainGroup']]['children'], reference)
        sources = put(prefix + 'sources', isa='PBXSourcesBuildPhase', buildActionMask='2147483647',
                      files=source_builds, runOnlyForDeploymentPostprocessing='0')
        frameworks = put(prefix + 'frameworks', isa='PBXFrameworksBuildPhase', buildActionMask='2147483647',
                         files=[], runOnlyForDeploymentPostprocessing='0')
        configurations = []
        for original in configs:
            base = original['buildSettings']
            settings = dict(PRODUCT_BUNDLE_IDENTIFIER=bundle + suffix, PRODUCT_NAME=product_name,
                INFOPLIST_FILE=product_name + '/Info.plist', CODE_SIGN_ENTITLEMENTS=product_name + '/Extension.entitlements',
                SWIFT_VERSION='5.0', SWIFT_OPTIMIZATION_LEVEL='-O' if original['name'] == 'Release' else '-Onone',
                APPLICATION_EXTENSION_API_ONLY='YES', SKIP_INSTALL='YES',
                ALWAYS_SEARCH_USER_PATHS='NO',
                IPHONEOS_DEPLOYMENT_TARGET='17.0', TARGETED_DEVICE_FAMILY='1,2', SDKROOT='iphoneos',
                LD_RUNPATH_SEARCH_PATHS=['$(inherited)', '@executable_path/Frameworks', '@executable_path/../../Frameworks'],
                MARKETING_VERSION=str(metadata['CFBundleShortVersionString']),
                CURRENT_PROJECT_VERSION=str(metadata['CFBundleVersion']))
            for name in ('DEVELOPMENT_TEAM', 'CODE_SIGN_STYLE', 'CODE_SIGN_IDENTITY'):
                if name in base:
                    settings[name] = base[name]
            configurations.append(put(prefix + original['name'], isa='XCBuildConfiguration',
                                      name=original['name'], buildSettings=settings))
        configuration_list = put(prefix + 'configurations', isa='XCConfigurationList',
            buildConfigurations=configurations, defaultConfigurationIsVisible='0', defaultConfigurationName='Release')
        product = put(prefix + 'product', isa='PBXFileReference', explicitFileType='wrapper.app-extension',
                      path=product_name + '.appex', sourceTree='BUILT_PRODUCTS_DIR', includeInIndex='0')
        target = put(prefix + 'target', isa='PBXNativeTarget', name=product_name, productName=product_name,
            productReference=product,
            productType='com.apple.product-type.extensionkit-extension' if extension_kit else 'com.apple.product-type.app-extension',
            buildConfigurationList=configuration_list, buildPhases=[sources, frameworks], buildRules=[], dependencies=[])
        proxy = put(prefix + 'proxy', isa='PBXContainerItemProxy', containerPortal=data['rootObject'],
                    proxyType='1', remoteGlobalIDString=target, remoteInfo=product_name)
        dependency = put(prefix + 'dependency', isa='PBXTargetDependency', target=target, targetProxy=proxy)
        embed_file = put(prefix + 'embed file', isa='PBXBuildFile', fileRef=product,
                         settings={'ATTRIBUTES': ['RemoveHeadersOnCopy']})
        embed = put(prefix + 'embed', isa='PBXCopyFilesBuildPhase', buildActionMask='2147483647',
                    dstPath='$(EXTENSIONS_FOLDER_PATH)' if extension_kit else '',
                    dstSubfolderSpec='16' if extension_kit else '13', name='Embed ' + product_name,
                    files=[embed_file], runOnlyForDeploymentPostprocessing='0')
        append_unique(project_object['targets'], target)
        append_unique(app.setdefault('dependencies', []), dependency)
        append_unique(app['buildPhases'], embed)
        append_unique(objects[project_object['productRefGroup']]['children'], product)
        for key in (app_id, target):
            attributes = project_object.setdefault('attributes', {}).setdefault('TargetAttributes', {}).setdefault(key, {})
            attributes.setdefault('SystemCapabilities', {})['com.apple.ApplicationGroups.iOS'] = {'enabled': 1}
    pbx.write_bytes(plistlib.dumps(data, sort_keys=False))
