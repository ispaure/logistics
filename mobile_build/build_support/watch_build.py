"""Native watchOS companion and complication for the existing Shortcut value store."""
from hashlib import sha256
import json
from pathlib import Path
import plistlib
import shutil

from .incoming_build import GROUP

ROOT = Path(__file__).resolve().parents[2]
WATCH_SUFFIXES = ('.watchkitapp', '.watchkitapp.widgets')
WATCH_FOLDERS = ('LogisticsWatch', 'LogisticsWatchWidget')


def configure(project, data):
    project = Path(project)
    objects = data['objects']
    owner = objects[data['rootObject']]
    app_id, app = next((key, obj) for key, obj in objects.items()
                       if obj.get('productType') == 'com.apple.product-type.application'
                       and obj.get('name') != 'LogisticsWatch')
    configs = [objects[key] for key in objects[app['buildConfigurationList']]['buildConfigurations']]
    bundle = configs[0]['buildSettings']['PRODUCT_BUNDLE_IDENTIFIER']
    metadata = plistlib.loads((project / 'LogisticsMobile/LogisticsMobile-Info.plist').read_bytes())

    def add(values, value):
        if value not in values:
            values.append(value)

    def put(identity, **value):
        key = sha256(('logistics.watch.' + identity).encode()).hexdigest()[:24].upper()
        objects[key] = value
        return key

    def sources(folder, names):
        destination = project / folder
        destination.mkdir(exist_ok=True)
        builds = []
        for relative in names:
            source = ROOT / relative
            shutil.copyfile(source, destination / source.name)
            reference = put(folder + source.name, isa='PBXFileReference',
                lastKnownFileType='sourcecode.c.objc' if source.suffix == '.m' else 'sourcecode.swift',
                path=folder + '/' + source.name, sourceTree='SOURCE_ROOT')
            add(objects[owner['mainGroup']]['children'], reference)
            builds.append(put(folder + source.name + ' build', isa='PBXBuildFile', fileRef=reference))
        return builds

    shared = ('Python/commonUtils/ui/native/ios/WidgetValueStore.swift',
              'Python/mobile/ios/widgets/WidgetSettings.swift', 'Python/mobile/ios/widgets/WatchValueSnapshot.swift')
    # The containing app retries persisted publications on launch and responds to Watch refresh requests.
    host_sources = sources('LogisticsWatchBridge', (*shared,
        'Python/mobile/ios/widgets/WatchValuePublisher.swift', 'Python/mobile/ios/widgets/WatchValueBootstrap.m',
        'Python/mobile/ios/widgets/SyncWatchValues.swift'))
    host_phase = next(objects[key] for key in app['buildPhases'] if objects[key]['isa'] == 'PBXSourcesBuildPhase')
    for build in host_sources:
        add(host_phase['files'], build)
    for config in configs:
        config['buildSettings'].setdefault('SWIFT_VERSION', '5.0')
        config['buildSettings']['ALWAYS_EMBED_SWIFT_STANDARD_LIBRARIES'] = 'YES'

    targets = []
    products = []
    for index, (folder, suffix) in enumerate(zip(WATCH_FOLDERS, WATCH_SUFFIXES)):
        widget = index == 1
        names = ('WatchValueWidget.swift',) if widget else ('LogisticsWatchApp.swift', 'WatchValueReceiver.swift')
        builds = sources(folder, (*shared, *('Python/mobile/ios/watch/' + name for name in names)))
        destination = project / folder
        info = dict(CFBundleDisplayName='Logistics', CFBundleName=folder,
            CFBundleExecutable='$(EXECUTABLE_NAME)', CFBundleIdentifier='$(PRODUCT_BUNDLE_IDENTIFIER)',
            CFBundlePackageType='XPC!' if widget else 'APPL',
            CFBundleShortVersionString=str(metadata['CFBundleShortVersionString']),
            CFBundleVersion=str(metadata['CFBundleVersion']))
        if widget:
            info['NSExtension'] = dict(NSExtensionPointIdentifier='com.apple.widgetkit-extension')
        else:
            info.update(WKApplication=True, WKCompanionAppBundleIdentifier=bundle,
                        WKRunsIndependentlyOfCompanionApp=False)
        (destination / 'Info.plist').write_bytes(plistlib.dumps(info))
        (destination / 'Watch.entitlements').write_bytes(plistlib.dumps({
            'com.apple.security.application-groups': [GROUP]}))
        phase = put(folder + ' sources', isa='PBXSourcesBuildPhase', buildActionMask='2147483647',
                    files=builds, runOnlyForDeploymentPostprocessing='0')
        frameworks = put(folder + ' frameworks', isa='PBXFrameworksBuildPhase', buildActionMask='2147483647',
                         files=[], runOnlyForDeploymentPostprocessing='0')
        phases = [phase, frameworks]
        if not widget:
            catalog = destination / 'Assets.xcassets'
            icon = catalog / 'AppIcon.appiconset'
            icon.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / 'mobile_build/resources/icons/ios/icon-1024.png', icon / 'icon.png')
            (catalog / 'Contents.json').write_text(json.dumps({'info': {'author': 'xcode', 'version': 1}}))
            (icon / 'Contents.json').write_text(json.dumps({'images': [
                {'filename': 'icon.png', 'idiom': 'universal', 'platform': 'watchos', 'size': '1024x1024'}],
                'info': {'author': 'xcode', 'version': 1}}))
            ref = put(folder + ' assets', isa='PBXFileReference', lastKnownFileType='folder.assetcatalog',
                      path=folder + '/Assets.xcassets', sourceTree='SOURCE_ROOT')
            add(objects[owner['mainGroup']]['children'], ref)
            build = put(folder + ' assets build', isa='PBXBuildFile', fileRef=ref)
            phases.append(put(folder + ' resources', isa='PBXResourcesBuildPhase', buildActionMask='2147483647',
                              files=[build], runOnlyForDeploymentPostprocessing='0'))
        configuration_keys = []
        for original in configs:
            settings = dict(PRODUCT_BUNDLE_IDENTIFIER=bundle + suffix, PRODUCT_NAME=folder,
                INFOPLIST_FILE=folder + '/Info.plist', CODE_SIGN_ENTITLEMENTS=folder + '/Watch.entitlements',
                SWIFT_VERSION='5.0', SWIFT_OPTIMIZATION_LEVEL='-O' if original['name'] == 'Release' else '-Onone',
                SDKROOT='watchos', SUPPORTED_PLATFORMS='watchos watchsimulator', WATCHOS_DEPLOYMENT_TARGET='10.0',
                TARGETED_DEVICE_FAMILY='4', SKIP_INSTALL='YES', ALWAYS_SEARCH_USER_PATHS='NO',
                LD_RUNPATH_SEARCH_PATHS=['$(inherited)', '@executable_path/Frameworks', '@executable_path/../../Frameworks'],
                MARKETING_VERSION=str(metadata['CFBundleShortVersionString']), CURRENT_PROJECT_VERSION=str(metadata['CFBundleVersion']))
            if widget:
                settings['APPLICATION_EXTENSION_API_ONLY'] = 'YES'
            else:
                settings['ASSETCATALOG_COMPILER_APPICON_NAME'] = 'AppIcon'
            for name in ('DEVELOPMENT_TEAM', 'CODE_SIGN_STYLE', 'CODE_SIGN_IDENTITY'):
                if name in original['buildSettings']:
                    settings[name] = original['buildSettings'][name]
            configuration_keys.append(put(folder + original['name'], isa='XCBuildConfiguration',
                                          name=original['name'], buildSettings=settings))
        configurations = put(folder + ' configurations', isa='XCConfigurationList',
            buildConfigurations=configuration_keys, defaultConfigurationIsVisible='0', defaultConfigurationName='Release')
        product = put(folder + ' product', isa='PBXFileReference',
            explicitFileType='wrapper.app-extension' if widget else 'wrapper.application',
            path=folder + ('.appex' if widget else '.app'), sourceTree='BUILT_PRODUCTS_DIR', includeInIndex='0')
        target = put(folder + ' target', isa='PBXNativeTarget', name=folder, productName=folder,
            productReference=product, productType='com.apple.product-type.app-extension' if widget else 'com.apple.product-type.application',
            buildConfigurationList=configurations, buildPhases=phases, buildRules=[], dependencies=[])
        add(owner['targets'], target)
        add(objects[owner['productRefGroup']]['children'], product)
        owner.setdefault('attributes', {}).setdefault('TargetAttributes', {}).setdefault(target, {}).setdefault(
            'SystemCapabilities', {})['com.apple.ApplicationGroups.iOS'] = {'enabled': 1}
        targets.append(target)
        products.append(product)

    for parent, target, product, folder, dst, subfolder in (
        (app, targets[0], products[0], WATCH_FOLDERS[0], '$(CONTENTS_FOLDER_PATH)/Watch', '16'),
        (objects[targets[0]], targets[1], products[1], WATCH_FOLDERS[1], '', '13'),
    ):
        proxy = put(folder + ' proxy', isa='PBXContainerItemProxy', containerPortal=data['rootObject'],
                    proxyType='1', remoteGlobalIDString=target, remoteInfo=folder)
        dependency = put(folder + ' dependency', isa='PBXTargetDependency', target=target, targetProxy=proxy)
        embed = put(folder + ' embed file', isa='PBXBuildFile', fileRef=product,
                    settings={'ATTRIBUTES': ['RemoveHeadersOnCopy']})
        phase = put(folder + ' embed', isa='PBXCopyFilesBuildPhase', buildActionMask='2147483647',
            dstPath=dst, dstSubfolderSpec=subfolder, name='Embed ' + folder, files=[embed], runOnlyForDeploymentPostprocessing='0')
        add(parent.setdefault('dependencies', []), dependency)
        add(parent['buildPhases'], phase)
