"""Provider document state and resource lifetime, separate from format commands."""


class ProviderDocumentSession:
    def __init__(self, owner):
        self.owner = owner
        self._reader = None
        self.metadata_fields = {}
        self.metadata_initial = {}
        self.metadata_values = {}
        self.closed = False

    @property
    def reader(self):
        return self._reader

    @reader.setter
    def reader(self, value):
        self._reader = value
        if value is not None:
            self.closed = False

    def dispose(self):
        """Called only after the workflow's busy/dirty guards have accepted close."""
        if self.closed:
            return
        owner = self.owner
        from .provider_ui import private_label
        for name in ('_provider_layout_task', '_provider_width_task'):
            task = getattr(owner, name, None)
            if task is not None:
                task.cancel()
                setattr(owner, name, None)
        if hasattr(owner, 'provider_epub_view'):
            owner.provider_epub_view.dispose()
            del owner.provider_epub_view
        owner._provider_epub_locations = {}
        search = getattr(owner, 'pdf_search', None)
        if search is not None:
            search.dispose()
        contents = getattr(owner, 'pdf_contents', None)
        if contents is not None:
            contents.dispose()
        reader = self.reader
        if reader is not None and reader.kind == '.pdf':
            reader.pdf.close()
            reader.data = b''
            from services.documents.readers import MemorySource
            if isinstance(reader.source, MemorySource):
                reader.source.data = b''
        from .page_animation import cancel_page_slide
        cancel_page_slide(getattr(owner, 'crypt_content', None))
        from .ios_content_background import clear
        clear(getattr(owner, 'app', owner))
        self._reader = None
        for field in self.metadata_fields.values():
            field.value = ''
        self.metadata_fields = {}
        self.metadata_initial = {}
        self.metadata_values = {}
        if hasattr(owner, 'crypt_metadata_view'):
            owner.crypt_metadata_view.content = None
            owner.crypt_metadata_status.text = ''
        workflow = getattr(owner, '_provider_markdown', None)
        if workflow is not None:
            workflow.dispose()
        if hasattr(owner, 'crypt_text'):
            owner.crypt_text.value = ''
            dispose = getattr(owner.crypt_text, 'dispose', None)
            if dispose is not None:
                dispose()
        if hasattr(owner, 'provider_spread'):
            owner.provider_spread.dispose()
        if hasattr(owner, 'crypt_image'):
            owner.crypt_image.dispose()
        if hasattr(owner, 'crypt_page'):
            owner.crypt_page.items = []
        if hasattr(owner, 'epub_session_bookmarks'):
            owner.epub_session_bookmarks.clear()
        if hasattr(owner, 'crypt_bookmarks'):
            owner.crypt_bookmarks.clear()
            owner.crypt_bookmark_selector.items = []
        if hasattr(owner, 'crypt_title'):
            owner.crypt_title.text = private_label('Encrypted copy closed')
        if hasattr(owner, 'crypt_password'):
            owner.crypt_password.value = ''
        from .external_display import sync as sync_external
        sync_external(getattr(owner, 'app', owner))
        self.closed = True
