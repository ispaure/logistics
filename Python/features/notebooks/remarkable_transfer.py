"""Local upload candidates and byte-level recovery checks; no device mutations.

A verified candidate is not a firmware capability or a remote commit receipt.
Native IDs remain unchanged; an importer must own collision and indexing rules.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO

from commonUtils.runtime.operations import check_cancelled

from .images import image_data, validate_png
from .notebook import Notebook
from .remarkable_export import export_rmdoc, needs_background_pdf
from .remarkable_ssh import UUID
from .templates import available


@dataclass(frozen=True)
class MemberDigest:
    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class UploadReceipt:
    document_id: str
    page_ids: tuple[str, ...]
    file_type: str
    source_sha256: str
    archive_sha256: str
    converted_backgrounds: bool
    members: tuple[MemberDigest, ...]


@dataclass(frozen=True)
class PreparedUpload:
    archive: bytes
    receipt: UploadReceipt


@dataclass(frozen=True)
class UploadComparison:
    missing: tuple[str, ...]
    changed: tuple[str, ...]
    unexpected: tuple[str, ...]

    @property
    def complete(self):
        """All member bytes match; this says nothing about firmware indexing."""
        return not (self.missing or self.changed or self.unexpected)


def _validate(book, cancelled):
    if 'cPages' in book.content and (type(book.content.get('formatVersion')) is not int or book.content['formatVersion'] != 2):
        raise ValueError('Modern page tables require formatVersion 2 for upload preparation; the source is unchanged.')
    if not UUID.fullmatch(book.id) or any(not UUID.fullmatch(page.id) for page in book.pages):
        raise ValueError('Upload preparation requires native document and page UUIDs.')
    if book.metadata.get('type') != 'DocumentType' or book.metadata.get('deleted') or book.metadata.get('parent') == 'trash':
        raise ValueError('Upload preparation requires a live document metadata record.')
    for name in book.members:
        check_cancelled(cancelled)
        root = name.split('/', 1)[0]
        if not (root == book.id or root.startswith(book.id + '.') or ('/' not in name and name.endswith('.template'))):
            raise ValueError('The archive contains members outside the selected document.')
    pdf_pages = None
    if book.content.get('fileType') == 'pdf':
        from pypdf import PdfReader
        try:
            pdf = PdfReader(BytesIO(book.members[book.id + '.pdf']))
            if pdf.is_encrypted:
                raise ValueError('Encrypted PDF backgrounds are not qualified for upload preparation.')
            pdf_pages = len(pdf.pages)
        except ValueError:
            raise
        except Exception as error:
            raise ValueError('The embedded PDF cannot be read for upload preparation.') from error
    for index, page in enumerate(book.pages):
        check_cancelled(cancelled)
        ink = book.page(index)
        if ink.warning:
            raise ValueError('Unsupported native page objects prevent upload preparation; the source is unchanged.')
        for _, data in image_data(book, index):
            check_cancelled(cancelled)
            validate_png(data)
        if pdf_pages is not None:
            redirect = page.record.get('redir', {}).get('value', -1)
            if redirect >= pdf_pages:
                raise ValueError('A page refers to a missing embedded PDF background.')
        elif not available(book, page):
            raise ValueError('A template is unavailable for upload preparation; the source is unchanged.')


def prepare_upload(data: bytes, *, cancelled=lambda: False) -> PreparedUpload:
    """Validate a bounded local RMDOC copy without choosing a remote destination.

    Known custom backgrounds use the existing portable PDF encoder. Otherwise
    return the exact input bytes. Never regenerate IDs or rewrite folder links.
    The stricter editable-format checks here do not constrain opaque retrieval.
    """
    check_cancelled(cancelled)
    if not isinstance(data, bytes):
        raise TypeError('Upload preparation accepts immutable archive bytes.')
    book = Notebook.read(data)
    _validate(book, cancelled)
    converted = needs_background_pdf(book)
    archive = export_rmdoc(book, cancelled=cancelled) if converted else data
    if converted:
        result = Notebook.read(archive)
        _validate(result, cancelled)
        # Only the known background export may change these sidecars. In
        # particular, page scenes, image resources and opaque members survive.
        editable = {book.id + suffix for suffix in ('.metadata', '.content', '.pagedata')}
        if any(result.members.get(name) != value for name, value in book.members.items() if name not in editable):
            raise ValueError('Upload preparation changed a preserved archive member.')
        book = result
    members = []
    for name, value in sorted(book.members.items()):
        check_cancelled(cancelled)
        members.append(MemberDigest(name, len(value), sha256(value).hexdigest()))
    check_cancelled(cancelled)
    receipt = UploadReceipt(book.id, tuple(page.id for page in book.pages),
                            book.content.get('fileType') or 'notebook', sha256(data).hexdigest(),
                            sha256(archive).hexdigest(), converted, tuple(members))
    return PreparedUpload(archive, receipt)


def compare_upload_members(receipt: UploadReceipt, observed: Mapping[str, bytes], *, cancelled=lambda: False) -> UploadComparison:
    """Compare a scoped staging copy with its receipt; never retry or clean it.

    Missing or changed bytes require recovery; unexpected members require
    ownership review. Even a complete comparison is not permission to publish.
    """
    expected = {member.name: member for member in receipt.members}
    changed = []
    for name, data in observed.items():
        check_cancelled(cancelled)
        member = expected.get(name)
        if member is not None and (len(data) != member.size or sha256(data).hexdigest() != member.sha256):
            changed.append(name)
    check_cancelled(cancelled)
    return UploadComparison(tuple(sorted(expected.keys() - observed.keys())), tuple(sorted(changed)),
                            tuple(sorted(observed.keys() - expected.keys())))
