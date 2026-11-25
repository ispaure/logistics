"""Platform PDF rendering adapter; document lifetime stays in the feature facade."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from pathlib import Path

from ..limits import PAGE_EDGE


class ApplePDF:
    def __init__(self, data):
        import ctypes
        from rubicon.objc import ObjCClass
        from rubicon.objc.runtime import autoreleasepool

        self.framework = ctypes.CDLL(
            "/System/Library/Frameworks/PDFKit.framework/PDFKit"
        )
        # Neighbor prefetch runs on a long-lived Python worker thread.
        with autoreleasepool():
            document = ObjCClass("PDFDocument").alloc()
            if isinstance(data, Path):
                self.document = document.initWithURL(ObjCClass("NSURL").fileURLWithPath(str(data)))
            else:
                self.document = document.initWithData(ObjCClass("NSData").dataWithBytes(data, length=len(data)))
        if self.document is None or self.document.isLocked:
            raise ValueError(
                "Cannot open PDF. It may be damaged or password protected."
            )
        self.count = int(self.document.pageCount)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.document = None

    def page_size(self, index):
        page = self.document.pageAtIndex(index)
        size = page.boundsForBox(1).size
        return (size.height, size.width) if page.rotation % 180 else (size.width, size.height)

    def select_text(self, index, start, end):
        from rubicon.objc import CGPoint
        from rubicon.objc.runtime import autoreleasepool

        with autoreleasepool():
            page = self.document.pageAtIndex(index)
            box = page.boundsForBox(1)
            left, bottom, w, h = box.origin.x, box.origin.y, box.size.width, box.size.height
            rotation = int(page.rotation) % 360

            def point(display):
                x, y = display
                x, y = {0: (x, y), 90: (y, 1 - x), 180: (1 - x, 1 - y), 270: (1 - y, x)}[rotation]
                return CGPoint(left + x * w, bottom + (1 - y) * h)

            def display(x, y):
                x, y = (x - left) / w, 1 - (y - bottom) / h
                return {0: (x, y), 90: (1 - y, x), 180: (1 - x, 1 - y), 270: (y, 1 - x)}[rotation]

            selection = (page.selectionForWordAtPoint(point(start)) if start == end else
                         page.selectionFromPoint(point(start), toPoint=point(end)))
            if selection is None or selection.string is None:
                return '', []
            lines = selection.selectionsByLine()
            rectangles = []
            for i in range(int(lines.count)):
                rect = lines.objectAtIndex(i).boundsForPage(page)
                x, y = rect.origin.x, rect.origin.y
                a, b = display(x, y), display(x + rect.size.width, y + rect.size.height)
                rectangles.append((min(a[0], b[0]), min(a[1], b[1]), abs(b[0] - a[0]), abs(b[1] - a[1])))
            return str(selection.string), rectangles

    def render(self, index, *, edge=PAGE_EDGE):
        import ctypes
        from rubicon.objc import CGSize
        from rubicon.objc.runtime import load_library
        from rubicon.objc.runtime import autoreleasepool
        from rubicon.objc import objc_id, ObjCInstance

        with autoreleasepool():
            image = self.document.pageAtIndex(index).thumbnailOfSize(
                CGSize(edge, edge), forBox=1
            )
            ui = load_library("UIKit")
            ui.UIImagePNGRepresentation.restype = objc_id
            ui.UIImagePNGRepresentation.argtypes = [objc_id]
            data = ObjCInstance(ui.UIImagePNGRepresentation(image))
            return ctypes.string_at(data.bytes, data.length)
