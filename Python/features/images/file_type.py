"""Image activation without importing image processing dependencies."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.filesystem.files import File


class ImageFile(File):
    browser_has_thumbnail = True

    def browser_thumbnail(self, size):
        from features.images.ui.decoding import image_thumbnail
        from services.documents.storage import read_local_bytes
        try:
            data = read_local_bytes(self.path, max_bytes=16 * 1024 * 1024)
        except ValueError:
            return b''
        return image_thumbnail(data, size)
