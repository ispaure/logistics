"""Modernize only the disposable clone of the pinned CPython iOS test app."""
import hashlib
import plistlib
import re
from pathlib import Path

SCENE_CLASS = 'LogisticsCoreTestSceneDelegate'
SCENE_SOURCE = '''
// Logistics compatibility for the pinned CPython testbed; not the runtime.
@interface LogisticsCoreTestSceneDelegate : UIResponder <UIWindowSceneDelegate>
@property (strong, nonatomic) UIWindow *window;
@end

@implementation LogisticsCoreTestSceneDelegate
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session
      options:(UISceneConnectionOptions *)connectionOptions {
    if (![scene isKindOfClass:[UIWindowScene class]]) { return; }
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    self.window.rootViewController = [[UIViewController alloc] init];
    [self.window makeKeyAndVisible];
}
@end
'''


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def modernize(testbed):
    """Preserve upstream XCTest/Python setup; add the app's required UI scene."""
    app = Path(testbed) / 'iOSTestbed'
    delegate, info = app / 'AppDelegate.m', app / 'iOSTestbed-Info.plist'
    text = delegate.read_text()
    data = plistlib.loads(info.read_bytes())
    configuration = {'UIWindowSceneSessionRoleApplication': [{
        'UISceneConfigurationName': 'Core runtime tests',
        'UISceneClassName': 'UIWindowScene', 'UISceneDelegateClassName': SCENE_CLASS}]}
    manifest = data.get('UIApplicationSceneManifest', {})
    existing = manifest.get('UISceneConfigurations', {})
    if existing and existing != configuration:
        raise ValueError('Unexpected upstream scene configuration; inspect before adapting.')
    if '@implementation AppDelegate' not in text:
        raise ValueError('Unexpected upstream testbed app delegate.')
    project = Path(testbed) / 'iOSTestbed.xcodeproj/project.pbxproj'
    project_text = project.read_text()
    target = re.compile(r'(IPHONEOS_DEPLOYMENT_TARGET = )(\d+(?:\.\d+)?)(;)')
    if not target.search(project_text):
        raise ValueError('Missing upstream deployment target; inspect before adapting.')
    project_text = target.sub(lambda match: match[1] + ('15.0' if float(match[2]) < 15 else match[2]) + match[3], project_text)
    before = {'delegate': digest(delegate), 'info': digest(info), 'project': digest(project)}
    if SCENE_CLASS not in text:
        delegate.write_text(text + SCENE_SOURCE)
    elif not text.endswith(SCENE_SOURCE):
        raise ValueError('Testbed scene adapter differs from the reviewed source.')
    data['UIApplicationSceneManifest'] = dict(manifest, UIApplicationSupportsMultipleScenes=False,
                                            UISceneConfigurations=configuration)
    info.write_bytes(plistlib.dumps(data))
    project.write_text(project_text)
    return dict(before=before, after={'delegate': digest(delegate), 'info': digest(info), 'project': digest(project)},
                adapter_sha256=digest(__file__), deployment_target='15.0')


def normalize_log(raw, output):
    """Strip only the upstream test app's system-log prefix, in either timezone."""
    prefix = re.compile(r'^\d{4}-\d{2}-\d{2}\s+\d+:\d{2}:\d{2}\.\d+[+-]\d{4}\s+iOSTestbed\[\d+:\w+\] ')
    text = Path(raw).read_text(encoding='utf-8', errors='backslashreplace')
    Path(output).write_text(''.join(prefix.sub('', line) for line in text.splitlines(keepends=True)), encoding='utf-8')


if __name__ == '__main__':
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('testbed', type=Path)
    print(json.dumps(modernize(parser.parse_args().testbed), indent=2))
