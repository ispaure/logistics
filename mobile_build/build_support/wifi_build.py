"""Platform declarations for opt-in foreground Wi-Fi session identification."""
from pathlib import Path
import plistlib
import subprocess


LOCATION_REASON = 'Identify your current Wi-Fi network for the optional trusted Wi-Fi session password setting. Logistics does not collect location updates.'


def configure_ios(project):
    project = Path(project)
    pbx = next(project.glob('*.xcodeproj/project.pbxproj'))
    try:
        data = plistlib.loads(pbx.read_bytes())
    except plistlib.InvalidFileException:
        data = plistlib.loads(subprocess.check_output(['plutil', '-convert', 'xml1', '-o', '-', str(pbx)]))
    objects = data['objects']
    apps = [obj for obj in objects.values() if obj.get('productType') == 'com.apple.product-type.application']
    if len(apps) != 1:
        raise ValueError('Expected one main application for Wi-Fi access.')
    configurations = objects[apps[0]['buildConfigurationList']]['buildConfigurations']
    for key in configurations:
        settings = objects[key]['buildSettings']
        relative = settings.get('CODE_SIGN_ENTITLEMENTS')
        if not relative or '$' in relative or Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise ValueError('Expected an owned main-app entitlement file for Wi-Fi access.')
        path = project / relative
        entitlements = plistlib.loads(path.read_bytes())
        entitlements['com.apple.developer.networking.wifi-info'] = True
        path.write_bytes(plistlib.dumps(entitlements))
    info = project / 'LogisticsMobile/LogisticsMobile-Info.plist'
    metadata = plistlib.loads(info.read_bytes())
    metadata['NSLocationWhenInUseUsageDescription'] = LOCATION_REASON
    info.write_bytes(plistlib.dumps(metadata))
