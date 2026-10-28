"""Small native host fixture for widget packaging and executable validation."""
from hashlib import sha256
from pathlib import Path
import plistlib


def make_project(root):
    root = Path(root)
    (root / 'WidgetProbe.xcodeproj').mkdir(parents=True)
    (root / 'LogisticsMobile').mkdir()
    (root / 'LogisticsMobile/main.m').write_text('''#import <UIKit/UIKit.h>
@interface ProbeDelegate : UIResponder <UIApplicationDelegate>
@property (strong, nonatomic) UIWindow *window;
@end
@implementation ProbeDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
    self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
    UIViewController *controller = [UIViewController new];
    controller.view.backgroundColor = UIColor.systemBackgroundColor;
    self.window.rootViewController = controller;
    [self.window makeKeyAndVisible];
    return YES;
}
@end
int main(int argc, char *argv[]) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(ProbeDelegate.class)); }
}
''')
    info = dict(CFBundleIdentifier='$(PRODUCT_BUNDLE_IDENTIFIER)', CFBundleExecutable='$(EXECUTABLE_NAME)',
                CFBundleName='Widget Probe', CFBundleDisplayName='Widget Probe', CFBundlePackageType='APPL',
                CFBundleVersion='123', CFBundleShortVersionString='1.0', LSRequiresIPhoneOS=True,
                UILaunchScreen={})
    (root / 'LogisticsMobile/LogisticsMobile-Info.plist').write_bytes(plistlib.dumps(info))
    (root / 'Main.entitlements').write_bytes(plistlib.dumps({'preserve-me': True}))
    objects = {}

    def put(identity, **values):
        key = sha256(identity.encode()).hexdigest()[:24].upper()
        objects[key] = values
        return key

    configurations = []
    project_configs = []
    for name in ('Debug', 'Release'):
        configurations.append(put(name, isa='XCBuildConfiguration', name=name, buildSettings=dict(
            PRODUCT_BUNDLE_IDENTIFIER='io.github.ispaure.logisticsmobile', PRODUCT_NAME='Widget Probe',
            INFOPLIST_FILE='LogisticsMobile/LogisticsMobile-Info.plist', CODE_SIGN_ENTITLEMENTS='Main.entitlements',
            SDKROOT='iphoneos', IPHONEOS_DEPLOYMENT_TARGET='17.0', TARGETED_DEVICE_FAMILY='1,2',
            CLANG_ENABLE_OBJC_ARC='YES', CODE_SIGN_STYLE='Automatic',
            OTHER_LDFLAGS=['-framework', 'UIKit'], ALWAYS_SEARCH_USER_PATHS='NO',
            CURRENT_PROJECT_VERSION='123', MARKETING_VERSION='1.0')))
        project_configs.append(put('project ' + name, isa='XCBuildConfiguration', name=name, buildSettings={}))
    config_list = put('configs', isa='XCConfigurationList', buildConfigurations=configurations,
                      defaultConfigurationIsVisible='0', defaultConfigurationName='Release')
    project_config_list = put('project configs', isa='XCConfigurationList', buildConfigurations=project_configs,
                              defaultConfigurationIsVisible='0', defaultConfigurationName='Release')
    source = put('source', isa='PBXFileReference', lastKnownFileType='sourcecode.c.objc',
                 path='LogisticsMobile/main.m', sourceTree='SOURCE_ROOT')
    build_source = put('build source', isa='PBXBuildFile', fileRef=source)
    sources = put('sources', isa='PBXSourcesBuildPhase', buildActionMask='2147483647',
                  files=[build_source], runOnlyForDeploymentPostprocessing='0')
    product = put('product', isa='PBXFileReference', explicitFileType='wrapper.application',
                  path='Widget Probe.app', sourceTree='BUILT_PRODUCTS_DIR', includeInIndex='0')
    target = put('app', isa='PBXNativeTarget', name='Widget Probe', productName='Widget Probe',
                 productReference=product, productType='com.apple.product-type.application',
                 buildConfigurationList=config_list, buildPhases=[sources], dependencies=[], buildRules=[])
    products = put('products', isa='PBXGroup', children=[product], sourceTree='<group>', name='Products')
    main = put('main', isa='PBXGroup', children=[source, products], sourceTree='<group>')
    project = put('project', isa='PBXProject', targets=[target], mainGroup=main, productRefGroup=products,
                  buildConfigurationList=project_config_list, compatibilityVersion='Xcode 14.0',
                  developmentRegion='en', knownRegions=['en', 'Base'], projectDirPath='', projectRoot='')
    path = root / 'WidgetProbe.xcodeproj/project.pbxproj'
    path.write_bytes(plistlib.dumps(dict(archiveVersion='1', objectVersion='56', classes={},
                                         rootObject=project, objects=objects)))
    return path
