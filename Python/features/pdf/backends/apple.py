"""Platform PDF rendering adapter; document lifetime stays in the feature facade."""

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
