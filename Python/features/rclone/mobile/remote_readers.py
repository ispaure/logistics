"""Format readers over an independently owned remote resource session."""
from pathlib import Path

from services.documents.readers import PrivateReader
from services.documents.mobile_reading import DocumentReadCapabilities
from features.rclone.remote_policy import direct_kind, TEXT_LIMIT
from .remote_source import RemoteSource as RemoteSource


class RemoteReaders:
    remote_storage = True
    document_capabilities = DocumentReadCapabilities(
        private=True, writable=False, credential_bound=True, offline=False, remote=True, required_feature='rclone')

    def capture_access(self, key):
        return self.resource.capture_access(key)

    @property
    def privacy_gate(self):
        return self.resource.privacy_gate

    def __init__(self, client, remote, *, progress=lambda message: None, resource=None, identity=None):
        from features.rclone.remote_access import NativeRemoteLocation
        from .service import native_service
        if resource is not None and (resource.client is not client or resource.remote != remote):
            raise ValueError('The remote view belongs to another connection.')
        self.resource = resource or native_service(client).remotes.open(NativeRemoteLocation(remote, identity=identity))
        self.client, self.remote = client, remote
        self.progress = progress
        self.root = self.resource.root

    def open(self, key, *, password='', cancelled=lambda: False):
        self.progress('Checking remote connection')
        resource = self.resource.reopen()
        source = RemoteSource(self.client, self.remote, key, password=password, cancelled=cancelled,
                              progress=self.progress, resource=resource, owns_resource=True)
        reader = None
        try:
            kind = direct_kind(key, source.size)
            if kind == 'text':
                with source.open(key) as stream:
                    reader = PrivateReader(key, stream.read(TEXT_LIMIT + 1))
                reader.source = source
            elif kind == 'image':
                with source.open(key) as stream:
                    data = stream.read()
                reader = RemoteImageReader(key, data, source)
            else:
                if Path(key).suffix.lower() in {'.epub', '.cbz', '.zip'}:
                    source.cache_archive()
                reader = PrivateReader(key, source=source)
            reader.key, reader.password, reader.read_only = key, password, True
            source.check()
            return reader
        except BaseException:
            from services.documents.mobile_reading import close_document_reader
            try:
                close_document_reader(reader)
            finally:
                source.close()
            raise



# Compatibility import for existing remote-reader callers.
from features.images.document import ImageReader as RemoteImageReader
