"""ComicInfo page records, preserving the existing line-based XML format."""

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
        """
        Updates comic pages in the ComicInfo.xml line list, from the provided image list (Page count & information for each page)
        """

        # Local helper can directly access cbz_image_file_lst and updated_line_lst
        def append_pages_lines():
            for page_number, cbz_image_file in enumerate(cbz_image_file_lst):
                page_line = cbz_image_file.get_comicinfo_xml_line(page_number)
                updated_line_lst.append(page_line)

        # Check that the list of line isn't 0 lines long, which means the lines were not previously loaded!
        if len(self.line_lst) == 0:
            log(Severity.ERROR, tool_name, 'Cannot Update Pages in ComicInfo.xml line List as it is empty and not loaded!')
            return False

        try:
            ElementTree.fromstring('\n'.join(self.line_lst))
        except ElementTree.ParseError as error:
            log(Severity.ERROR, tool_name, f'Invalid ComicInfo.xml: {error}')
            return False

        went_through_pages_section = False  # Update once have written the page lines
        updated_line_lst = []
        in_page_section = False

        for line in self.line_lst:
            if line.startswith('  <PageCount>'):
                updated_line_lst.append(f'  <PageCount>{len(cbz_image_file_lst)}</PageCount>')
                continue
            if not in_page_section:
                if line == '  <Pages />':
                    log(Severity.WARNING, tool_name, 'ComicInfoXML.update_pages_in_line_lst: Hit the <Pages /> line, meaning no page information was previously registered. Repairing...')
                    updated_line_lst.append('  <Pages>')
                    append_pages_lines()
                    updated_line_lst.append('  </Pages>')
                    went_through_pages_section = True
                elif line == '  <Pages>':
                    updated_line_lst.append(line)
                    append_pages_lines()
                    in_page_section = True
                else:
                    updated_line_lst.append(line)
            else:
                if line == '  </Pages>':
                    updated_line_lst.append(line)
                    in_page_section = False
                    went_through_pages_section = True

        if not went_through_pages_section:
            log(Severity.ERROR, tool_name, f'Did not go through Pages Section of ComicInfo.XML! {self.line_lst}')
            return False

        try:
            root = ElementTree.fromstring('\n'.join(updated_line_lst))
            pages = root.findall('./Pages/Page')
            if len(pages) != len(cbz_image_file_lst):
                raise ValueError('ComicInfo page records do not match image count')
            if root.findtext('PageCount') != str(len(cbz_image_file_lst)):
                raise ValueError('ComicInfo PageCount was not updated')
        except (ElementTree.ParseError, ValueError) as error:
            log(Severity.ERROR, tool_name, f'Invalid updated ComicInfo.xml: {error}')
            return False

        self.line_lst = updated_line_lst
        return True


