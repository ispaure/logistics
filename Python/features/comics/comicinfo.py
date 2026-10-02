"""Structural ComicInfo page updates with consistent XML formatting."""

from __future__ import annotations
from pathlib import Path
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
            serialized = ElementTree.tostring(root, encoding='utf-8', xml_declaration=True)
            validated = ElementTree.fromstring(serialized)
            if len(validated.findall(f'{pages_tag}/{namespace}Page')) != len(cbz_image_file_lst):
                raise ValueError('ComicInfo page records do not match image count')
            if validated.findtext(count_tag) != str(len(cbz_image_file_lst)):
                raise ValueError('ComicInfo PageCount was not updated')
        except (ElementTree.ParseError, ValueError) as error:
            log(Severity.ERROR, tool_name, f'Invalid ComicInfo.xml: {error}')
            return False

        self.line_lst = serialized.decode('utf-8').splitlines()
        return True
