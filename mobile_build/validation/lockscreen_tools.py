"""Run the real resume form on leased devices using the owning deployment helper."""
import argparse
import json
import os
from pathlib import Path
import shutil

from logistics_build.build_retention import scratch
from mobile_build.deployment import manager_settings
from mobile_build.tools import stage
from mobile_build.validation import document_storage_tools as focused


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform', choices=('ios', 'android'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--android-image', help='Explicit installed system-image identifier; uses the manager profile by default.')
    parser.add_argument('--ios-app', type=Path, help='Reuse an exact-native-source managed shell; restage current Python and tests.')
    parser.add_argument('--retain-on-failure', action='store_true', help='Pin the owned build for diagnosis; remove the pin and workspace after retrying.')
    parser.add_argument('--family', choices=('iPhone', 'iPad'), default='iPhone')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    options, _ = manager_settings.settings(focused.REPO / 'mobile_build')
    if args.android_image:
        options['android.image'] = args.android_image
    env = dict(os.environ, DEVELOPER_DIR=options['tools.xcode'], ANDROID_HOME=options['tools.android_sdk'],
               ANDROID_SDK_ROOT=options['tools.android_sdk'], JAVA_HOME=options['tools.java'])
    env['PATH'] = str(focused.REPO / 'mobile_build/.tools/go/bin') + os.pathsep + env['PATH']
    os.environ.update(env)
    with scratch(focused.REPO) as workspace:
        os.environ['LOGISTICS_DEPLOY_WORKSPACE'] = env['LOGISTICS_DEPLOY_WORKSPACE'] = str(workspace)
        os.environ['COMMONUTILS_STORAGE_ROOT'] = env['COMMONUTILS_STORAGE_ROOT'] = str(workspace / 'storage')
        env['XDG_CACHE_HOME'] = str(workspace / 'probe-tools')
        shutil.copyfile(focused.REPO / 'mobile_build/pyproject.toml', workspace / 'pyproject.toml')
        payload = workspace / 'payload'
        (output / 'source.json').write_text(json.dumps(stage(focused.REPO, payload, allow_dirty=True), indent=2))
        profile = dict(bundle='io.github.ispaure.logisticsnotebookqa',
                       entry_point='tests.logisticsmobile.lockscreen_probe', result_name='lockscreen-result.json')
        try:
            if args.platform == 'ios':
                focused.run_ios(workspace, payload, output, env, family=args.family, source_app=args.ios_app, **profile)
            else:
                focused.run_android(workspace, payload, output, env, options, **profile)
        except BaseException:
            if args.retain_on_failure:
                (workspace / '.keep').touch()
                (output / 'retained-build.json').write_text(json.dumps(dict(workspace=str(workspace))))
            raise



if __name__ == '__main__':
    main()
