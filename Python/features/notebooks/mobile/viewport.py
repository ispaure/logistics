"""Device-class hints for the notebook's responsive paper defaults."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.ui.native.text_size import native_backend


def tablet_viewport(web):
    """Use native device identity where available; browser geometry is fallback."""
    if web is None:
        return None
    backend = native_backend(web)
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        return int(ObjCClass('UIDevice').currentDevice.userInterfaceIdiom) == 1
    if backend.startswith('toga_android.'):
        configuration = web._impl.native.getResources().getConfiguration()
        return int(configuration.smallestScreenWidthDp) >= 600
    return None
