"""Memory-only file previews shared by the desktop and mobile library panes."""
from base64 import b64encode
from html import escape
from pathlib import PurePosixPath
from dataclasses import dataclass
from commonUtils.runtime.operations import check_cancelled
from services.documents.storage import DocumentResource, document_operation


@dataclass(frozen=True)
class PreviewContent:
    name: str
    size: int
    image: bytes = b''
    mime: str = ''
    text: str = ''
    video_url: str = ''

    def html(self):
        if self.video_url:
            body = ('<h1>' + escape(self.name) + '</h1>'
                    '<video controls playsinline preload="none" style="width:100%;max-height:75vh" src="'
                    + escape(self.video_url, quote=True) + '">Video playback is unavailable.</video>')
        elif self.image:
            mime = self.mime
            body = '<img alt="' + escape(self.name, quote=True) + '" src="data:' + mime + ';base64,' + b64encode(self.image).decode('ascii') + '">'
        else:
            body = '<h1>' + escape(self.name) + '</h1><p>' + escape(self.text) + '</p>'
        return ('<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">'
                '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; '
                'img-src data:; media-src http://127.0.0.1:*; base-uri \'none\'; form-action \'none\'">'
                '<style>:root{color-scheme:light dark}body{font:16px sans-serif;margin:12px;background:Canvas;color:CanvasText}img{max-width:100%;height:auto}</style></head><body>'
                + body + '<p>' + f'{self.size:,} bytes' + '</p></body></html>')


class FilePreview:
    def __init__(self, path, size):
        self.path, self.size = path, size
        self.document, self.image = None, b''
        self.mime, self.text, self.count = '', '', 1
        self.video, self.transport = None, None

    @property
    def video_url(self):
        return self.transport.url if self.transport is not None else ''

    @classmethod
    def open(cls, provider, path, *, cancelled=lambda: False):
        from features.images.document import IMAGE_EXTENSIONS
        from features.video.formats import VIDEO_EXTENSIONS
        suffix = PurePosixPath(path).suffix.lower()
        result = None
        try:
            with document_operation(provider, cancelled):
                row = provider.entry(path)
                if row['directory']:
                    raise ValueError('Choose a file.')
                result = cls(path, row['size'])
                if suffix in VIDEO_EXTENSIONS:
                    from features.video.playback import VideoContent
                    from features.video.transport import VideoTransport
                    result.video = VideoContent(provider, path)
                    result.transport = VideoTransport(result.video)
                elif suffix == '.pdf':
                    from features.pdf.document import PDFDocument, MAX_PDF
                    with DocumentResource(provider, path, max_bytes=MAX_PDF) as resource:
                        result.document = PDFDocument(resource.read(cancelled=cancelled))
                    result.count = result.document.count
                elif suffix in IMAGE_EXTENSIONS | {'.gif'}:
                    from features.images.validation import MAX_IMAGE, image_dimensions
                    from commonUtils.formats.image_headers import image_header, gif_header
                    with DocumentResource(provider, path, max_bytes=MAX_IMAGE) as resource:
                        result.image = resource.read(cancelled=cancelled)
                    if suffix == '.gif':
                        header = gif_header(result.image, max_bytes=MAX_IMAGE)
                        if not (0 < header.width <= 8192 and 0 < header.height <= 8192
                                and header.width * header.height <= 16_000_000):
                            raise ValueError('Image exceeds the 16-megapixel limit.')
                        kind = 'gif'
                    else:
                        image_dimensions(result.image)
                        kind = image_header(result.image, max_bytes=MAX_IMAGE).format
                    result.mime = 'image/' + ('jpeg' if kind == 'jpg' else kind)
                else:
                    result.text = 'No preview is available for this file type.'
                check_cancelled(cancelled)
                return result
        except BaseException:
            if result is not None:
                result.close()
            raise

    def content(self, index=0):
        if not 0 <= index < self.count:
            raise ValueError('Page does not exist.')
        image = self.document.page(index) if self.document is not None else self.image
        mime = 'image/png' if self.document is not None else self.mime
        return PreviewContent(PurePosixPath(self.path).name, self.size, image, mime, self.text, self.video_url)

    def page(self, index=0):
        """HTML adapter retained for mobile publication and existing callers."""
        return self.content(index).html()

    def close(self):
        if self.transport is not None:
            self.transport.close()
            self.transport = None
        if self.video is not None:
            self.video.close()
            self.video = None
        if self.document is not None:
            self.document.close()
            self.document = None
        self.image, self.text, self.path = b'', '', ''
