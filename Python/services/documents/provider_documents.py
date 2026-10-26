"""Storage-neutral mobile reader/editor adapter over one resource provider."""
from pathlib import Path

from commonUtils.runtime.resources.content import ProviderContent
from commonUtils.runtime.streams import read_up_to
from services.documents.mobile_reading import DocumentReadCapabilities
from services.documents.storage import DocumentPolicy, DocumentResource, document_writable


class ProviderDocuments:
    def __init__(self, provider):
        self.provider = provider

    @property
    def privacy_gate(self):
        return getattr(self.provider, 'privacy_gate', None)

    def capture_access(self, key):
        capture = getattr(self.provider, 'capture_access', None)
        if capture is not None:
            return capture(key)
        from services.documents.storage import check_document_access
        return lambda: check_document_access(self.provider)

    @property
    def document_capabilities(self):
        declared = getattr(self.provider, 'document_capabilities', None)
        if declared is not None:
            return declared
        policy = DocumentPolicy.for_provider(self.provider)
        return DocumentReadCapabilities(not policy.persistent, document_writable(self.provider),
                                        not policy.persistent, self.offline)

    @property
    def offline(self):
        return not getattr(self.provider, 'remote_storage', False)

    def open(self, key, *, password='', cancelled=lambda: False, read_provider=None):
        from commonUtils.archives.zip_access import ArchivePasswordError
        content = ProviderContent(read_provider or self.provider, key, password=password, cancelled=cancelled)
        try:
            from features.images.document import IMAGE_EXTENSIONS, ImageReader
            if Path(key).suffix.lower() in IMAGE_EXTENSIONS:
                from features.images.validation import MAX_IMAGE
                with content.open(key) as stream:
                    data = read_up_to(stream, MAX_IMAGE + 1, cancelled=cancelled)
                reader = ImageReader(Path(key).name, data, content)
            elif Path(key).suffix.lower() not in {'.pdf', '.epub', '.cbz', '.zip'}:
                with content.open(key) as stream:
                    data = read_up_to(stream, 1024 * 1024 + 1, cancelled=cancelled)
                if len(data) > 1024 * 1024:
                    raise ValueError('Text editing is limited to 1 MiB.')
                from features.text_editor.resources import TextReader
                reader = TextReader(Path(key).name, data, key=key, revision=content.expected)
            else:
                from services.documents.readers import PrivateReader
                try:
                    reader = PrivateReader(Path(key).name, source=content, path=key)
                except ArchivePasswordError:
                    configured = getattr(self.provider, 'archive_password', None)
                    if password or configured is None:
                        raise
                    password = configured(key, cancelled=cancelled)
                    if not password:
                        raise
                    content.close()
                    content = ProviderContent(self.provider, key, password=password, cancelled=cancelled)
                    reader = PrivateReader(Path(key).name, source=content, path=key)
            reader.source = content
            reader.key, reader.revision, reader.document_revision = key, content.expected, content.expected
            reader.password = password
            reader.read_only = not document_writable(self.provider, reader)
            content.check()
            return reader
        except BaseException:
            content.close()
            raise

    def save(self, reader, text, *, cancelled=lambda: False):
        if not reader.editable or not document_writable(self.provider, reader):
            raise PermissionError('This document is read-only.')
        source = reader.source
        source.check()
        data = reader.text_snapshot.encode(text)
        # The retained source's provider preserves its original credential grant.
        return DocumentResource.publish(source.provider, source.path, data,
            max_bytes=1024 * 1024, expected_revision=source.expected, cancelled=cancelled,
            after_publish=lambda revision: self.open(source.path))

    def save_metadata(self, reader, changes, *, cancelled=lambda: False):
        if not document_writable(self.provider, reader):
            raise PermissionError('This document is read-only.')
        if reader.kind == '.epub':
            from features.books.mutations import metadata_plan
            member, data = metadata_plan(reader.book, changes)
        else:
            from features.comics.mutations import metadata_plan
            member, data = metadata_plan(reader.comic, changes)
        source = reader.source
        source.check()
        source.provider.replace_archive_members(source.path, {member: data},
            expected_revision=source.expected, password=reader.password, cancelled=cancelled)
        from commonUtils.runtime.operations import MutationIncomplete, MutationResult
        try:
            return self.open(source.path, password=reader.password)
        except Exception as error:
            raise MutationIncomplete('Metadata was saved, but the document could not reopen. Keep your draft.',
                                     MutationResult(destination_published=True)) from error
