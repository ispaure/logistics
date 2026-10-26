"""Bounded image documents and folder-scoped navigation over resource providers."""
from pathlib import PurePosixPath

IMAGE_EXTENSIONS = frozenset({'.png', '.jpg', '.jpeg', '.webp'})


class ImageReader:
    editable = False
    book = None
    read_only = True
    image_document = True

    def __init__(self, name, data, source):
        from .validation import image_dimensions
        image_dimensions(data)
        self.name, self.data, self.source = name, data, source
        self.kind = PurePosixPath(name).suffix.lower()
        self.labels = [PurePosixPath(name).name]

    def page(self, index):
        if index != 0:
            raise ValueError('Image does not exist.')
        check = getattr(self.source, 'check', None)
        if check is not None:
            check()
        return 'image', self.data


def folder_images(rows, current):
    folder = PurePosixPath(current).parent
    return [(row['path'], row['name']) for row in rows
            if not row['directory'] and PurePosixPath(row['path']).parent == folder
            and PurePosixPath(row['name']).suffix.lower() in IMAGE_EXTENSIONS]


def adjacent_image(rows, current, direction):
    from commonUtils.filesystem.traversal import natural_path_key
    images = sorted(folder_images(rows, current), key=lambda item: natural_path_key(PurePosixPath(item[1])))
    index = next((i for i, item in enumerate(images) if item[0] == current), None)
    if index is None:
        return None
    target = index + (1 if direction > 0 else -1)
    return images[target][0] if 0 <= target < len(images) else None
