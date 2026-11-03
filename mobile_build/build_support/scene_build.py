"""Configure system scenes in the pinned generated iOS project."""
from pathlib import Path
import plistlib
import shutil


def configure(project):
    candidates = list(Path(project).glob('*/*-Info.plist'))
    if len(candidates) != 1:
        raise ValueError('Expected one generated app Info.plist for scene configuration.')
    path = candidates[0]
    data = plistlib.loads(path.read_bytes())
    manifest = data.setdefault('UIApplicationSceneManifest', {})
    manifest['UIApplicationSupportsMultipleScenes'] = True
    configurations = manifest.setdefault('UISceneConfigurations', {})
    for role, name in (
        ('UIWindowSceneSessionRoleApplication', 'Logistics workspace'),
        ('UIWindowSceneSessionRoleExternalDisplayNonInteractive', 'Logistics comic display'),
        ('UIWindowSceneSessionRoleExternalDisplay', 'Logistics comic display'),
    ):
        configurations[role] = [dict(UISceneConfigurationName=name,
            UISceneClassName='UIWindowScene', UISceneDelegateClassName='LogisticsSceneDelegate')]
    data['UIApplicationSceneManifest'] = manifest
    path.write_bytes(plistlib.dumps(data, sort_keys=False))
    launcher = Path(project) / 'LogisticsMobile' / 'main.m'
    source = Path(__file__).resolve().parents[2] / 'Python/commonUtils/ui/native/ios/ScrollingTitle.m'
    support = Path(project) / 'Support'
    support.mkdir(exist_ok=True)
    shutil.copyfile(source, support / source.name)
    include = '#import "../Support/ScrollingTitle.m"'
    previous = launcher.read_text()
    text = previous
    if include not in text:
        text = include + '\n' + text
    original = 'UIApplicationMain(argc, argv, nil, @"PythonAppDelegate")'
    replacement = 'UIApplicationMain(argc, argv, nil, @"LogisticsSceneAppDelegate")'
    if original in text:
        if text.count(original) != 1:
            raise ValueError('Unexpected iOS launcher delegate declaration.')
        text = text.replace(original, replacement)
    elif text.count(replacement) != 1:
        raise ValueError('Expected the tracked scene delegate in the iOS launcher.')
    if text != previous:
        launcher.write_text(text)


if __name__ == '__main__':
    import sys
    configure(sys.argv[1])
