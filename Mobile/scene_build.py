"""Configure system scenes in the pinned generated iOS project."""
from pathlib import Path
import plistlib


def configure(project):
    candidates = list(Path(project).glob('*/*-Info.plist'))
    if len(candidates) != 1:
        raise ValueError('Expected one generated app Info.plist for scene configuration.')
    path = candidates[0]
    data = plistlib.loads(path.read_bytes())
    manifest = data.setdefault('UIApplicationSceneManifest', {})
    manifest['UIApplicationSupportsMultipleScenes'] = True
    data['UIApplicationSceneManifest'] = manifest
    path.write_bytes(plistlib.dumps(data, sort_keys=False))
    launcher = Path(project) / 'LogisticsMobile' / 'main.m'
    text = launcher.read_text()
    original = 'UIApplicationMain(argc, argv, nil, @"PythonAppDelegate")'
    replacement = 'UIApplicationMain(argc, argv, nil, @"LogisticsSceneAppDelegate")'
    if original in text:
        if text.count(original) != 1:
            raise ValueError('Unexpected iOS launcher delegate declaration.')
        launcher.write_text(text.replace(original, replacement))
    elif text.count(replacement) != 1:
        raise ValueError('Expected the tracked scene delegate in the iOS launcher.')


if __name__ == '__main__':
    import sys
    configure(sys.argv[1])
