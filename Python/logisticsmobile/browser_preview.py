"""Mobile domain previews over provider streams; shared widgets own presentation."""
import base64
from pathlib import Path
from commonUtils.runtime.operations import check_cancelled
from .crypt_stream import NativeSource


def callbacks(provider, client, password=''):
    def source(row, cancelled):
        path = provider._guard(provider._locate(row['path']))
        return NativeSource(client, provider.record(row['path']), path, password=password, cancelled=cancelled)

    def thumbnail(row, size, cancelled):
        check_cancelled(cancelled)
        if not getattr(client, 'supports_streaming', False):
            return b''
        suffix = Path(row['path']).suffix.lower()
        if getattr(provider, 'private', False):
            item = source(row, cancelled)
            member = ''
            if suffix in {'.zip', '.cbz', '.epub'}:
                from .localcrypt import PrivateReader
                reader = PrivateReader(item.name, source=item)
                member = reader.book.cover_path() if reader.book else reader.pages[0]
                if not member:
                    return b''
            elif suffix not in {'.png', '.jpg', '.jpeg', '.webp'}:
                return b''
            data = item.request('crypt_thumbnail', member=member, width=size[0], height=size[1])
        elif suffix in {'.png', '.jpg', '.jpeg', '.webp'}:
            with provider.open(row['path']) as stream:
                data = client.request('file_thumbnail', fd=stream.fileno(), width=size[0], height=size[1])
        else:
            # Ordinary ZIP/EPUB cover bytes also stay in memory.
            from zipfile import ZipFile
            from features.comics.mobile.validation import image_dimensions
            member_data = None
            if suffix in {'.zip', '.cbz'}:
                from features.comics.pages import natural_key
                with provider.open(row['path']) as stream, ZipFile(stream) as archive:
                    pages = sorted((info for info in archive.infolist() if Path(info.filename).suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'}), key=lambda info: natural_key(info.filename))
                    if pages and pages[0].file_size <= 8 * 1024 * 1024:
                        member_data = archive.read(pages[0])
            elif suffix == '.epub':
                from features.books.epub import EPUBBook
                book = EPUBBook(provider.root / row['path'], source=provider)
                if book.cover_path():
                    member_data = book.read(book.cover_path())
            if not member_data:
                return b''
            # Descriptor-backed native resizing without a plaintext disk cache.
            # In-memory cover conversion is provided by the native bridge action.
            image_dimensions(member_data)
            data = client.request('image_thumbnail', data=base64.b64encode(member_data).decode(), width=size[0], height=size[1])
        check_cancelled(cancelled)
        return base64.b64decode(data['data'], validate=True)

    def details(row, cancelled):
        check_cancelled(cancelled)
        suffix = Path(row['path']).suffix.lower()
        fields = []
        if suffix in {'.zip', '.cbz', '.epub'}:
            if getattr(provider, 'private', False):
                from .localcrypt import PrivateReader
                reader = PrivateReader(Path(row['path']).name, source=source(row, cancelled))
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
