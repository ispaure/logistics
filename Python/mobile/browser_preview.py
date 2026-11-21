"""Mobile domain previews over provider streams; shared widgets own presentation."""
import base64
from functools import lru_cache
from pathlib import Path
from commonUtils.runtime.operations import check_cancelled
from contextlib import closing
from commonUtils.runtime.resources.content import ProviderContent
from commonUtils.runtime.resources.local import LocalFiles


DIRECT_IMAGE_SUFFIXES = frozenset({'.png', '.jpg', '.jpeg', '.webp', '.gif'})
ARCHIVE_SUFFIXES = frozenset({'.zip', '.cbz', '.epub'})
PREVIEW_SUFFIXES = DIRECT_IMAGE_SUFFIXES | ARCHIVE_SUFFIXES | {'.pdf', '.rmdoc'}


@lru_cache(maxsize=1)
def local_image_bridge():
    # The descriptor/image bridge works even with Connections disabled or locked.
    from features.rclone.mobile.cloud import CloudClient
    return CloudClient()


class LocalThumbnails:
    """An offline provider snapshot, scoped to the browser's access and revision."""
    def __init__(self, provider, client, password):
        self.provider, self.client, self.password = provider, client, password
        capabilities = getattr(provider, 'document_capabilities', None)
        self.private = getattr(provider, 'private', False)
        self.enabled = (isinstance(provider, LocalFiles)
                        and not getattr(provider, 'remote_storage', False)
                        and (not self.private or (getattr(capabilities, 'offline', False)
                             and not getattr(capabilities, 'remote', False)
                             and callable(getattr(provider, 'thumbnail', None)))))
        self.thumbnail, self.details = callbacks(provider, client, password)

    def supports(self, entry):
        return (self.enabled and not entry.container and entry.revision is not None
                and not entry.payload.get('cached') and entry.suffix.lower() in PREVIEW_SUFFIXES)

    def can_publish(self):
        if self.private:
            try:
                self.provider.check()
            except (OSError, ValueError):
                return False
        return self.enabled

    def load(self, row, size, cancelled):
        try:
            return self._load(row, size, cancelled)
        except (OSError, ValueError):
            return b''

    def _load(self, row, size, cancelled):
        from services.documents.storage import DocumentResource, document_operation
        path = row['path']
        suffix = Path(path).suffix.lower()
        if (not self.enabled or row.get('directory') or row.get('cached')
                or row.get('revision') is None or suffix not in PREVIEW_SUFFIXES):
            return b''
        check_cancelled(cancelled)
        provider = self.provider
        with document_operation(provider, cancelled):
            if not self.private:
                from commonUtils.filesystem.network import is_network_location
                if is_network_location(provider.transfer_location(path)):
                    return b''
            if provider.entry(path)['revision'] != row['revision']:
                return b''
            if suffix in {'.pdf', '.rmdoc'}:
                from features.pdf.document import MAX_PDF, PDFDocument
                with DocumentResource(provider, path, max_bytes=MAX_PDF, independent=False) as resource:
                    data = resource.read(cancelled=cancelled)
                if suffix == '.rmdoc':
                    from features.notebooks.thumbnail import notebook_thumbnail
                    data = notebook_thumbnail(data, max(size), cancelled=cancelled)
                else:
                    data = PDFDocument.render_page(data, 0, edge=max(size))
            else:
                data = self.thumbnail(row, size, cancelled)
            check_cancelled(cancelled)
            return data if provider.entry(path)['revision'] == row['revision'] else b''


def callbacks(provider, client, password=''):
    def source(row, cancelled):
        return ProviderContent(provider, row['path'], password=password, cancelled=cancelled)

    def thumbnail(row, size, cancelled):
        check_cancelled(cancelled)
        suffix = Path(row['path']).suffix.lower()
        native_thumbnail = getattr(provider, 'thumbnail', None)
        if native_thumbnail is not None:
            member = ''
            if suffix in ARCHIVE_SUFFIXES:
                from services.documents.readers import PrivateReader
                with closing(source(row, cancelled)) as content:
                    reader = PrivateReader(Path(row['path']).name, source=content, path=row['path'])
                    member = reader.book.cover_path() if reader.book else reader.pages[0]
                if not member:
                    return b''
            return native_thumbnail(row['path'], size, member=member, password=password, cancelled=cancelled)
        bridge = client if getattr(client, 'supports_streaming', False) else local_image_bridge()
        if suffix in DIRECT_IMAGE_SUFFIXES:
            with provider.open(row['path']) as stream:
                data = bridge.request('file_thumbnail', fd=stream.fileno(), width=size[0], height=size[1])
        else:
            # Ordinary ZIP/EPUB cover bytes also stay in memory.
            member_data = None
            if suffix in {'.zip', '.cbz'}:
                from zipfile import ZipFile
                from commonUtils.archives.zip_access import open_archive
                from features.comics.collection.pages import page_names
                with provider.open(row['path']) as stream:
                    opener = open_archive(stream, password=password) if password else ZipFile(stream)
                    with opener as archive:
                        pages = page_names(archive)
                        if pages and archive.getinfo(pages[0]).file_size <= 8 * 1024 * 1024:
                            member_data = archive.read(pages[0])
            elif suffix == '.epub':
                from features.books.epub import EPUBBook
                book = EPUBBook(provider.root / row['path'], source=provider)
                if book.cover_path():
                    member_data = book.read(book.cover_path())
            if not member_data:
                return b''
            if len(member_data) > 8 * 1024 * 1024:
                return b''
            check_cancelled(cancelled)
            data = bridge.request('image_thumbnail', data=base64.b64encode(member_data).decode(),
                                  width=size[0], height=size[1])
        check_cancelled(cancelled)
        return base64.b64decode(data['data'], validate=True)

    def details(row, cancelled):
        check_cancelled(cancelled)
        suffix = Path(row['path']).suffix.lower()
        fields = []
        if suffix in {'.zip', '.cbz', '.epub'}:
            if getattr(provider, 'private', False):
                from services.documents.readers import PrivateReader
                with closing(source(row, cancelled)) as content:
                    reader = PrivateReader(Path(row['path']).name, source=content, path=row['path'])
                    if reader.book:
                        fields = [('Title', reader.book.title), ('Author', ', '.join(reader.book.values('creator')))]
                    else:
                        fields = [('Pages', len(reader.pages))]
                        fields += [(field, reader.comic.info.get_field(field)) for field in ('Title', 'Series', 'Writer', 'Publisher', 'Summary') if reader.comic.info.get_field(field)]
            elif suffix == '.epub':
                from features.books.epub import EPUBBook
                book = EPUBBook(provider.root / row['path'], source=provider)
                fields = [('Title', book.title), ('Author', ', '.join(book.values('creator')))]
            else:
                from features.comics.library import ComicDocument
                document = ComicDocument(provider.root / row['path'], source=provider, password=password or None)
                fields = [(field, document.info.get_field(field)) for field in ('Title', 'Series', 'Writer', 'Publisher', 'Summary') if document.info.get_field(field)]
        check_cancelled(cancelled)
        return fields
    return thumbnail, details
