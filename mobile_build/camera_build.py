"""Install the images owner's native camera into the generated iOS launcher."""
from pathlib import Path
import shutil
import plistlib


def configure(project):
    project = Path(project)
    source = Path(__file__).resolve().parents[1] / 'Python/features/images/mobile/ios/BurstCamera.m'
    support = project / 'Support'
    support.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, support / 'BurstCamera.m')
    launcher = project / 'LogisticsMobile/main.m'
    text = launcher.read_text()
    include = '#import "../Support/BurstCamera.m"'
    if include not in text:
        launcher.write_text(text.replace('#import <UIKit/UIKit.h>', '#import <UIKit/UIKit.h>\n' + include))
    info = project / 'LogisticsMobile/LogisticsMobile-Info.plist'
    data = plistlib.loads(info.read_bytes())
    data['NSCameraUsageDescription'] = 'Capture photos immediately and take bursts from Home.'
    data['NSPhotoLibraryAddUsageDescription'] = 'Save your burst camera photos directly to your Photos library.'
    info.write_bytes(plistlib.dumps(data, sort_keys=False))
