"""Build a standalone iOS simulator test app inside its owned recipe."""
import json
import os
from pathlib import Path
import plistlib
import re
import sys
from uuid import uuid4

from build_manager.native_commands import command
from build_manager.retention import linked
from logistics_build.device_workspace_paths import DEVICE_WORKSPACES
from logistics_build.mobile_payload import stage_payload
from mobile_build.deployment.deployment_paths import prepare_workspace


def recipe_binding(root, workspace):
    return dict(schema=1, platform='ios', kind='simulator-build', workspace=str(workspace), root=str(root))


def build_paths(root, workspace, result):
    if not workspace.is_absolute() or '..' in workspace.parts:
        raise ValueError('Simulator build requires an absolute owned workspace.')
    if len(workspace.parents) < 5:
        raise ValueError('Simulator build paths do not match the owned workspace.')
    owner = workspace.parents[4]
    if (workspace.parent != owner / DEVICE_WORKSPACES / 'ios'
            or not re.fullmatch('[0-9a-f]{32}', workspace.name)
            or root.parent != owner / 'mobile_build/.tools/build-manager/snapshots'
            or result != workspace / 'build.json'):
        raise ValueError('Simulator build paths do not match the owned workspace.')
    recipe = workspace / 'recipe.json'
    generated = workspace / 'build/logisticsmobile/ios/xcode'
    derived = workspace / 'build/derived'
    app = derived / 'Build/Products/Debug-iphonesimulator/Logistics Mobile.app'
    paths = (root, recipe, result, workspace / 'pyproject.toml', workspace / 'native_tests',
             workspace / 'payload', generated / 'Logistics Mobile.xcodeproj/project.pbxproj',
             generated / 'LogisticsMobile/LogisticsMobile-Info.plist', derived, app,
             workspace / 'build/manager-ios-cache.json')
    if any(linked(part) for path in paths for part in (path, *path.parents)):
        raise ValueError('Simulator build refuses linked workspace paths.')
    if recipe.stat().st_size > 262144 or json.loads(recipe.read_text()) != recipe_binding(root, workspace):
        raise ValueError('Simulator recipe does not match its captured paths.')
    return generated, derived, app


def compile_app(root, workspace, generated, derived):
    mobile = root / 'mobile_build'
    prepare_workspace(mobile, workspace=workspace)
    stage_payload(root, sys.executable, command, workspace=workspace)
    cloud = ['/usr/bin/env', 'LOGISTICS_DEPLOY_WORKSPACE=' + str(workspace),
             sys.executable, str(mobile / 'cloud_build.py')]
    command([*cloud, 'licenses', '--platform', 'ios'], workspace)
    pbx = generated / 'Logistics Mobile.xcodeproj'
    briefcase = [sys.executable, '-m', 'briefcase']
    if not (pbx / 'project.pbxproj').is_file():
        command([*briefcase, 'create', 'iOS', '--no-input'], workspace)
    command([*briefcase, 'update', 'iOS', '--test', '--update-requirements', '--no-input'], workspace)
    command([*cloud, 'ios'], workspace)
    info = generated / 'LogisticsMobile/LogisticsMobile-Info.plist'
    data = plistlib.loads(info.read_bytes())
    data['MainModule'] = 'tests.logisticsmobile'
    info.write_bytes(plistlib.dumps(data))
    command(['xcodebuild', '-project', str(pbx), '-scheme', 'Logistics Mobile', '-configuration', 'Debug',
             '-sdk', 'iphonesimulator', '-destination', 'generic/platform=iOS Simulator',
             '-derivedDataPath', str(derived), '-resultBundlePath', str(derived / (uuid4().hex + '.xcresult')),
             'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-', 'CODE_SIGN_STYLE=Manual',
             'DEVELOPMENT_TEAM=', 'ARCHS=' + os.uname().machine, 'build'], workspace)
