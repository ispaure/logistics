"""Install native camera features into the generated iOS launcher."""
from pathlib import Path
import shutil
import plistlib


def configure(project):
    project = Path(project)
    python = Path(__file__).resolve().parents[2] / 'Python'
    source = python / 'features/images/mobile/ios/BurstCamera.m'
    support = project / 'Support'
    support.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, support / 'BurstCamera.m')
    cover = python / 'mobile/ios/ReaderCoverDisplay.m'
    shutil.copyfile(cover, support / cover.name)
    launcher = project / 'LogisticsMobile/main.m'
    text = launcher.read_text()
    include = '#import "../Support/BurstCamera.m"'
    previous = text
    for header in (include, '#import "../Support/ReaderCoverDisplay.m"'):
        if header not in text:
            text = text.replace('#import <UIKit/UIKit.h>', '#import <UIKit/UIKit.h>\n' + header)
    if text != previous:
        launcher.write_text(text)
    info = project / 'LogisticsMobile/LogisticsMobile-Info.plist'
    data = plistlib.loads(info.read_bytes())
    data['NSCameraUsageDescription'] = 'Take photos from Home or power the optional outer-display cover while reading.'
    data['NSPhotoLibraryAddUsageDescription'] = 'Save your burst camera photos directly to your Photos library.'
    info.write_bytes(plistlib.dumps(data, sort_keys=False))
