"""Qt-independent EPUB package, reading order and navigation.

Resources stay inside their ZIP; no book content is extracted to disk. Limits
bound decompression and XML parsing. Metadata writes live in metadata.py.
"""
from dataclasses import dataclass
from pathlib import Path
import posixpath
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET
from zipfile import ZipFile, BadZipFile

OPF = 'http://www.idpf.org/2007/opf'
DC = 'http://purl.org/dc/elements/1.1/'
XHTML = 'http://www.w3.org/1999/xhtml'
EPUB = 'http://www.idpf.org/2007/ops'
MAX_RESOURCE = 32 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_MEMBERS = 20000


class BookError(ValueError):
    """A book cannot be read or safely updated."""


def resolve_href(base, href):
    """Resolve an archive-local URL, rejecting external and escaping paths."""
    url = urlsplit(href)
    if url.scheme or url.netloc:
        raise BookError('Only resources inside the EPUB can be opened.')
    path = unquote(url.path)
    if '\\' in path or '\x00' in path or path.startswith('/'):
        raise BookError('Invalid resource path in EPUB.')
    joined = posixpath.normpath(posixpath.join(posixpath.dirname(base), path)) if path else base
    if joined in ('.', '..') or joined.startswith('../'):
        raise BookError('A resource path escapes the EPUB archive.')
    return joined, unquote(url.fragment)


def parse_xml(data):
    try:
        # Preserve comments, processing instructions and unknown metadata.
        return ET.fromstring(data, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True)))
    except ET.ParseError as error:
        raise BookError(f'Invalid EPUB XML: {error}') from error


@dataclass(frozen=True)
class Chapter:
    label: str
    path: str
    fragment: str = ''
    depth: int = 0


class EPUBBook:
    """Immutable loaded package with lazy, bounded chapter/resource reads."""
    def __init__(self, path):
        # Editing a symlink must update its target, rather than replacing the link
        # with a new archive and leaving the original book's metadata unchanged.
        self.path = Path(path).resolve(strict=True)
        try:
            with ZipFile(self.path) as archive:
                infos = archive.infolist()
                self.members = {info.filename for info in infos}
                if len(infos) > MAX_MEMBERS or sum(info.file_size for info in infos) > MAX_TOTAL:
                    raise BookError('This EPUB exceeds the supported archive size limits.')
                if len(self.members) != len(infos):
                    raise BookError('The EPUB has duplicate archive entries.')
                if any(info.flag_bits & 1 for info in infos):
                    raise BookError('Encrypted EPUB archives are not supported.')
                if self._read(archive, 'mimetype').strip() != b'application/epub+zip':
                    raise BookError('This file is not an EPUB book.')
                container = parse_xml(self._read(archive, 'META-INF/container.xml'))
                rootfile = next((node for node in container.iter() if isinstance(node.tag, str)
                                 and node.tag.endswith('}rootfile') and
                                 node.get('media-type') == 'application/oebps-package+xml'), None)
                if rootfile is None:
                    raise BookError('The EPUB has no package document.')
                self.package_path, _ = resolve_href('', rootfile.get('full-path', ''))
                self.package_bytes = self._read(archive, self.package_path)
                self.package = parse_xml(self.package_bytes)
                self.metadata_node = self.package.find(f'{{{OPF}}}metadata')
                if self.metadata_node is None:
                    raise BookError('The EPUB has no metadata section.')
                manifest = self.package.find(f'{{{OPF}}}manifest')
                spine = self.package.find(f'{{{OPF}}}spine')
                if manifest is None or spine is None:
                    raise BookError('The EPUB has no reading order.')
                self.manifest = {item.get('id'): item for item in manifest if item.tag == f'{{{OPF}}}item'}
                self.spine = []
                for ref in spine:
                    if ref.tag != f'{{{OPF}}}itemref':
                        continue
                    item = self.manifest.get(ref.get('idref'))
                    if item is None:
                        raise BookError('The EPUB reading order refers to a missing item.')
                    if item.get('media-type') == 'application/xhtml+xml':
                        resource, _ = resolve_href(self.package_path, item.get('href', ''))
                        if resource not in self.members:
                            raise BookError(f'Missing chapter: {resource}')
                        self.spine.append(resource)
                if not self.spine:
                    raise BookError('This EPUB has no supported text chapters (fixed-layout SVG books are not supported).')
                if 'META-INF/encryption.xml' in self.members:
                    encryption = parse_xml(self._read(archive, 'META-INF/encryption.xml'))
                    for node in encryption.iter():
                        if isinstance(node.tag, str) and node.tag.endswith('}CipherReference'):
                            resource, _ = resolve_href('', node.get('URI', ''))
                            if resource in self.spine:
                                raise BookError('DRM-encrypted chapters are not supported.')
                self.chapters = self._navigation(archive, spine)
                self.signature = self._signature()
        except (BadZipFile, KeyError, UnicodeError) as error:
            raise BookError(f'Cannot read EPUB: {error}') from error

    def _signature(self):
        info = self.path.stat()
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns

    @staticmethod
    def _read(archive, name):
        info = archive.getinfo(name)
        if info.file_size > MAX_RESOURCE:
            raise BookError('An EPUB resource exceeds the 32 MB reading limit.')
        with archive.open(info) as stream:
            data = stream.read(MAX_RESOURCE + 1)
        if len(data) > MAX_RESOURCE:
            raise BookError('An EPUB resource exceeds the reading limit.')
        return data

    def read(self, name):
        if self._signature() != self.signature:
            raise BookError('This book changed on disk. Reopen it before continuing.')
        try:
            with ZipFile(self.path) as archive:
                return self._read(archive, name)
        except (BadZipFile, KeyError) as error:
            raise BookError(f'Cannot read EPUB resource: {error}') from error

    def values(self, name):
        return [(node.text or '').strip() for node in self.metadata_node.findall(f'{{{DC}}}{name}')]

    @property
    def title(self):
        return next(iter(self.values('title')), '') or self.path.stem

    def cover_path(self):
        """Resolve an EPUB 3 cover-image or EPUB 2 cover metadata/guide reference."""
        item = next((item for item in self.manifest.values()
                     if 'cover-image' in item.get('properties', '').split()), None)
        if item is None:
            cover_id = next((node.get('content') for node in self.metadata_node.findall(f'{{{OPF}}}meta')
                             if node.get('name', '').lower() == 'cover'), None)
            item = self.manifest.get(cover_id)
        if item is not None:
            path, _ = resolve_href(self.package_path, item.get('href', ''))
            if item.get('media-type', '').startswith('image/') and path in self.members:
                return path
        guide = self.package.find(f'{{{OPF}}}guide')
        reference = next((node for node in (guide if guide is not None else ()) if node.get('type') == 'cover'), None)
        path = resolve_href(self.package_path, reference.get('href', ''))[0] if reference is not None else self.spine[0]
        if any(item.get('media-type', '').startswith('image/') and
               resolve_href(self.package_path, item.get('href', ''))[0] == path for item in self.manifest.values()):
            return path if path in self.members else None
        # Older books often identify a cover XHTML page instead of the image.
        document = parse_xml(self.read(path))
        image = next(iter(document.iter(f'{{{XHTML}}}img')), None)
        if image is not None:
            target, _ = resolve_href(path, image.get('src', ''))
            if target in self.members:
                return target
        return None

    def _navigation(self, archive, spine):
        chapters = []
        nav = next((item for item in self.manifest.values() if 'nav' in item.get('properties', '').split()), None)
        if nav is not None:
            path, _ = resolve_href(self.package_path, nav.get('href', ''))
            document = parse_xml(self._read(archive, path))
            toc = next((node for node in document.iter(f'{{{XHTML}}}nav')
                        if 'toc' in node.get(f'{{{EPUB}}}type', '').split()), None)
            if toc is not None:
                def visit(node, depth=0):
                    if node.tag == f'{{{XHTML}}}a':
                        target, fragment = resolve_href(path, node.get('href', ''))
                        if target in self.spine:
                            chapters.append(Chapter(''.join(node.itertext()).strip() or Path(target).stem,
                                                    target, fragment, max(0, depth - 1)))
                    for child in node:
                        visit(child, depth + (child.tag == f'{{{XHTML}}}ol'))
                visit(toc)
        if not chapters:
            ncx = self.manifest.get(spine.get('toc'))
            if ncx is not None:
                path, _ = resolve_href(self.package_path, ncx.get('href', ''))
                doc = parse_xml(self._read(archive, path))
                ns = {'n': 'http://www.daisy.org/z3986/2005/ncx/'}
                def visit(point, depth=0):
                    content = point.find('n:content', ns)
                    label = point.find('n:navLabel/n:text', ns)
                    if content is not None:
                        target, fragment = resolve_href(path, content.get('src', ''))
                        if target in self.spine:
                            chapters.append(Chapter(label.text if label is not None and label.text else Path(target).stem,
                                                    target, fragment, depth))
                    for child in point.findall('n:navPoint', ns):
                        visit(child, depth + 1)
                for point in doc.findall('n:navMap/n:navPoint', ns):
                    visit(point)
        represented = {chapter.path for chapter in chapters}
        chapters.extend(Chapter(Path(path).stem.replace('_', ' '), path) for path in self.spine if path not in represented)
        return chapters
