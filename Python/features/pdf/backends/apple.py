"""Platform PDF rendering adapter; document lifetime stays in the feature facade."""

from ..limits import PAGE_EDGE


class ApplePDF:
    def __init__(self, data):
        import ctypes
        from rubicon.objc import ObjCClass

        self.framework = ctypes.CDLL(
            "/System/Library/Frameworks/PDFKit.framework/PDFKit"
        )
        self.document = (
            ObjCClass("PDFDocument")
            .alloc()
            .initWithData(ObjCClass("NSData").dataWithBytes(data, length=len(data)))
        )
        if self.document is None or self.document.isLocked:
            raise ValueError(
                "Cannot open PDF. It may be damaged or password protected."
            )
        self.count = int(self.document.pageCount)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.document = None

    def render(self, index):
        import ctypes
        from rubicon.objc import CGSize
        from rubicon.objc.runtime import load_library
        from rubicon.objc import objc_id, ObjCInstance

        image = self.document.pageAtIndex(index).thumbnailOfSize(
            CGSize(PAGE_EDGE, PAGE_EDGE), forBox=1
        )
        ui = load_library("UIKit")
        ui.UIImagePNGRepresentation.restype = objc_id
        ui.UIImagePNGRepresentation.argtypes = [objc_id]
        data = ObjCInstance(ui.UIImagePNGRepresentation(image))
        return ctypes.string_at(data.bytes, data.length)
