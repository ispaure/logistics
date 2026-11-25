"""Configure system scenes in the pinned generated iOS project."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

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
    awake = Path(__file__).resolve().parents[2] / 'Python/mobile/ios/ScreenAwake.m'
    shutil.copyfile(awake, support / awake.name)
    pencil = Path(__file__).resolve().parents[2] / 'Python/features/notebooks/mobile/ios/NotebookInputWindow.m'
    shutil.copyfile(pencil, support / pencil.name)
    photos = pencil.with_name('NotebookPhotoPicker.m')
    shutil.copyfile(photos, support / photos.name)
    include = '#import "../Support/ScrollingTitle.m"'
    previous = launcher.read_text()
    text = previous
    for native in (pencil, photos):
        native_include = f'#import \"../Support/{native.name}\"'
        if native_include not in text:
            text = native_include + '\n' + text
    awake_include = '#import "../Support/ScreenAwake.m"'
    if awake_include not in text:
        text = awake_include + '\n' + text
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
