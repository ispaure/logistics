"""Logistics policy for the disposable pinned CPython iOS test app."""
from build_manager import cpython_testbed

SCENE_CLASS = 'LogisticsCoreTestSceneDelegate'
SCENE_SOURCE = cpython_testbed.scene_source(SCENE_CLASS,
    comment='Logistics compatibility for the pinned CPython testbed; not the runtime.')
digest = cpython_testbed.digest
normalize_log = cpython_testbed.normalize_log


def modernize(testbed):
    import json
    from pathlib import Path
    settings = json.loads(Path(__file__).with_name('mobile_runtime_tools.json').read_text())['preparation']
    return cpython_testbed.modernize(testbed, scene_class=SCENE_CLASS, scene_source=SCENE_SOURCE,
        deployment_target=settings['ios_deployment_target'], adapter_sha256=digest(__file__))


if __name__ == '__main__':
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('testbed', type=Path)
    print(json.dumps(modernize(parser.parse_args().testbed), indent=2))
