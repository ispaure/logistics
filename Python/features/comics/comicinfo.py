"""Structural ComicInfo page updates with consistent XML formatting."""

from __future__ import annotations
from pathlib import Path
import re
from xml.etree import ElementTree
from typing import TYPE_CHECKING, List
from commonUtils.debugUtils import Severity, log
from commonUtils.fileTypes import xmlType
if TYPE_CHECKING:
    from .cbz import CBZImageFile

tool_name = "features.comics.cbz"


class ComicInfoXML(xmlType.XMLFile):
    def __init__(self, path: Path):
        super().__init__(path)

    def read_lines(self) -> List[str]:
        # Unicode line separators are valid XML text, not file line endings.
        with self.path.open('r', encoding='utf-8-sig') as source:
            self.line_lst = source.read().split('\n')
        return self.line_lst

    def update_pages_in_line_lst(self, cbz_image_file_lst: List[CBZImageFile]) -> bool:
        """Rebuild page records while preserving other metadata and XML comments."""
        if not self.line_lst:
            log(Severity.ERROR, tool_name, 'Cannot update unloaded/empty ComicInfo.xml')
            return False

        try:
            parser = ElementTree.XMLParser(target=ElementTree.TreeBuilder(
                insert_comments=True, insert_pis=True))
            root = ElementTree.fromstring('\n'.join(self.line_lst), parser=parser)
            if root.tag.rsplit('}', 1)[-1] != 'ComicInfo':
                raise ValueError('Expected a ComicInfo root element')
            namespace = root.tag.rsplit('}', 1)[0] + '}' if root.tag.startswith('{') else ''
            count_tag, pages_tag = namespace + 'PageCount', namespace + 'Pages'
            counts, sections = root.findall(count_tag), root.findall(pages_tag)
            if len(counts) > 1 or len(sections) > 1:
                raise ValueError('Duplicate PageCount or Pages elements')

            # IMPORTANT: ComicRack compatibility requirement — DO NOT DELETE this
            # comment or replace this rebuild with a merge of old page records.
            # After modifying page files, stale page indices, byte sizes, dimensions,
            # and per-page metadata must not survive. The maintainer reports that
            # retaining this information can make ComicRack crash on opening the
            # modified comic (2026-10-08). On 2026-10-02, in the chat "Switch folder
            # sources to tabs", they explicitly chose to discard page attributes:
            # "ok yeah it's ok to not preserve the attributes, id rather have it
            # that way." Drop ALL old Pages children, including comments, PIs,
            # bookmarks, DoublePage flags and custom per-page metadata; synthesize
            # records only from the final images below, with page zero FrontCover.
            # This rule concerns compression that changes page files. Book metadata
            # and comments outside Pages remain; metadata-only editing leaves the
            # image bytes unchanged and uses a separate tree. See README.md's
            # "ComicRack compatibility: rebuilding page records" for evidence.
            if sections:
                pages = sections[0]
                for child in list(pages):
                    pages.remove(child)
                pages.text = None
            else:
                pages = ElementTree.SubElement(root, pages_tag)
            if counts:
                count = counts[0]
                if len(count):
                    raise ValueError('PageCount must contain only text')
            else:
                count = ElementTree.Element(count_tag)
                root.insert(list(root).index(pages), count)
            count.text = str(len(cbz_image_file_lst))

            # Keep the established page attribute policy, including FrontCover.
            for page_number, image in enumerate(cbz_image_file_lst):
                page = ElementTree.fromstring(image.get_comicinfo_xml_line(page_number))
                page.tag = namespace + 'Page'
                pages.append(page)

            ElementTree.indent(root, space='  ')
            serialized = ElementTree.tostring(root, encoding='utf-8', xml_declaration=True).decode('utf-8')
            # ElementTree emits literal CRs in text; XML readers would normalize
            # them to LF. Preserve CRs originally supplied as character references.
            serialized = serialized.replace('\r', '&#13;')
            validated = ElementTree.fromstring(serialized)
            if len(validated.findall(f'{pages_tag}/{namespace}Page')) != len(cbz_image_file_lst):
                raise ValueError('ComicInfo page records do not match image count')
            if validated.findtext(count_tag) != str(len(cbz_image_file_lst)):
                raise ValueError('ComicInfo PageCount was not updated')
        except (ElementTree.ParseError, ValueError) as error:
            log(Severity.ERROR, tool_name, f'Invalid ComicInfo.xml: {error}')
            return False

        self.line_lst = serialized.split('\n')
        return True

    # Metadata editing deliberately uses its own tree, separate from line_lst.
    FIELDS = (
        'Title', 'Series', 'Number', 'Count', 'Volume', 'AlternateSeries',
        'AlternateNumber', 'AlternateCount', 'Summary', 'Notes', 'Year', 'Month',
        'Day', 'Writer', 'Penciller', 'Inker', 'Colorist', 'Letterer', 'CoverArtist',
        'Editor', 'Translator', 'Publisher', 'Imprint', 'Genre', 'Tags', 'Web', 'PageCount',
        'LanguageISO', 'Format', 'BlackAndWhite', 'Manga', 'Characters', 'Teams',
        'Locations', 'ScanInformation', 'StoryArc', 'StoryArcNumber', 'SeriesGroup',
        'AgeRating', 'CommunityRating', 'MainCharacterOrTeam', 'Review', 'GTIN',
    )

    @classmethod
    def from_bytes(cls, data: bytes):
        document = super().from_bytes(data)
        if document.xml_root.localName != 'ComicInfo':
            raise ValueError('Expected a ComicInfo root element')
        return document

    # Sequence follows the Anansi v2.1 draft; existing nodes are never reordered.
    SCHEMA_ORDER = list(FIELDS)
    SCHEMA_ORDER.insert(SCHEMA_ORDER.index('CommunityRating'), 'Pages')

    INTEGER_MAXIMUMS = dict.fromkeys(('Count', 'Volume', 'AlternateCount', 'Year'), 2147483647)
    INTEGER_MAXIMUMS.update(Month=12, Day=31)
    INTEGER_FIELDS = frozenset(INTEGER_MAXIMUMS)
    ENUMS = {
        'BlackAndWhite': ('Unknown', 'No', 'Yes'),
        'Manga': ('Unknown', 'No', 'Yes', 'YesAndRightToLeft'),
        'AgeRating': ('Unknown', 'Adults Only 18+', 'Early Childhood', 'Everyone',
                      'Everyone 10+', 'G', 'Kids to Adults', 'M', 'MA15+',
                      'Mature 17+', 'PG', 'R18+', 'Rating Pending', 'Teen', 'X18+'),
    }

    def get_field(self, field: str) -> str:
        if field not in self.FIELDS:
            raise ValueError(f'Unsupported ComicInfo field: {field}')
        return self.get_text(field)

    def set_field(self, field: str, value: str):
        """Validate changed ComicInfo fields; preserve untouched legacy values."""
        if field == 'PageCount':
            raise ValueError('PageCount is maintained by the compression workflow')
        original = self.get_field(field)
        if not isinstance(value, str):
            raise TypeError('ComicInfo field values must be strings')
        if original == value:
            return
        if value and field in self.INTEGER_FIELDS:
            if not re.fullmatch(r'[+-]?[0-9]+', value):
                raise ValueError(f'{field} must be an integer or blank')
            number = int(value)
            upper = self.INTEGER_MAXIMUMS[field]
            if not -1 <= number <= upper:
                raise ValueError(f'{field} must be between -1 and {upper}, or blank')
        if value and field in self.ENUMS and value not in self.ENUMS[field]:
            raise ValueError(f'Unsupported {field} value: {value}')
        is_new = self._text_element(field) is None
        self.set_text(field, value)
        if is_new and value:
            # Insert a new known field in schema order without touching extensions.
            element = self._text_element(field)
            position = self.SCHEMA_ORDER.index(field)
            root = self.xml_root
            for sibling in list(root.childNodes):
                if (sibling is not element and sibling.nodeType == sibling.ELEMENT_NODE
                        and sibling.namespaceURI == root.namespaceURI
                        and sibling.localName in self.SCHEMA_ORDER
                        and self.SCHEMA_ORDER.index(sibling.localName) > position):
                    root.insertBefore(element, sibling)
                    break

    @property
    def metadata(self) -> dict[str, str]:
        return {field: self.get_field(field) for field in self.FIELDS}



def _metadata_property(field):
    return property(lambda self: self.get_field(field),
                    lambda self, value: self.set_field(field, value))


# Expose Python-style properties such as writer, series and age_rating.
for _field in ComicInfoXML.FIELDS:
    _name = re.sub(r'(?<!^)(?=[A-Z][a-z])|(?<=[a-z])(?=[A-Z])', '_', _field).lower()
    setattr(ComicInfoXML, _name, _metadata_property(_field))
