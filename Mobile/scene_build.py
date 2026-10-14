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


if __name__ == '__main__':
    import sys
    configure(sys.argv[1])
