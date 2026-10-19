"""Disposable native evidence for filled controls and navigable hierarchies."""
import asyncio
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace as NS
import traceback
from uuid import uuid4

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from logisticsmobile.app import LogisticsMobile
from tests.logisticsmobile.fixtures import capture_window


class Probe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('surface-hierarchy-' + uuid4().hex)
        super().startup()

    def on_running(self):
        if not getattr(self, '_surface_probe', False):
            self._surface_probe = True
            self.loop.create_task(self.probe())

    async def probe(self):
        from logisticsmobile.appearance import hierarchy_row_style
        from logisticsmobile.control_icons import icon_button
        from logisticsmobile.documentation_ui import show_documentation
        from features.books.mobile.navigation import ChapterList
        from features.pdf.mobile.contents import PDFContents
        from pypdf import PdfWriter
        output = Path(self.paths.cache) / 'surface-hierarchy-evidence'
        output.mkdir(exist_ok=True)
        report = dict(success=False, samples=[])
        ios = type(self._impl).__module__.startswith('toga_iOS.')
        try:
            await asyncio.sleep(1)
            root = (output / 'docs').resolve()
            (root / 'getting-started').mkdir(parents=True, exist_ok=True)
            (root / 'docs.md').write_text('# Documentation')
            (root / 'getting-started/getting-started.md').write_text('# Getting started')
            (root / 'getting-started/connections.md').write_text('# Connecting your folders')
            (root / 'getting-started/reading.md').write_text('# Reading and writing')
            (root / 'reference.md').write_text('# Reference')
            entries = [NS(label=label, depth=depth, index=index) for label, depth, index in (
                ('Part One — Getting started', 0, 0), ('Welcome', 1, 1),
                ('Connecting your folders', 1, 2), ('Reading and writing', 1, 3),
                ('Part Two — Reference', 0, 4), ('Keyboard shortcuts', 1, 5), ('Appendix', 0, 6))]
            writer = PdfWriter()
            for _ in range(4):
                writer.add_blank_page(width=100, height=100)
            parent = writer.add_outline_item('Getting started', 0)
            writer.add_outline_item('Connecting your folders', 1, parent=parent)
            writer.add_outline_item('Reference', 2)
            stream = BytesIO()
            writer.write(stream)
            themes = ('light', 'dark') if ios else ('system',)
            for theme in themes:
                if ios:
                    self.main_window._impl.native.overrideUserInterfaceStyle = 2 if theme == 'dark' else 1
                await asyncio.sleep(.3)
                actions = toga.Box(style=Pack(direction=COLUMN, margin=16, flex=1))
                actions.add(toga.Label('Your documents', style=Pack(font_size=26, margin_bottom=16)))
                for label in ('New document', 'Open from Files', 'Import a book', 'Connection settings'):
                    actions.add(toga.Button(label, on_press=lambda w: None, style=Pack(height=48, margin_bottom=8)))
                toolbar = toga.Box(children=[icon_button(kind, label) for kind, label in (
                    ('save', 'Save'), ('find', 'Find'), ('more', 'Actions'))], style=Pack(direction=ROW, margin_top=16))
                actions.add(toolbar)
                self.show_view(actions, checkpoint=False, destination='documents', route='surface-qa', title='Actions')
                await asyncio.sleep(.6)
                for button in actions.children[1:5]:
                    assert button._impl._surface_roles == ('surface', 'text', False)
                    if ios:
                        assert float(button._impl.native.layer.borderWidth) == 0
                await capture_window(self, output / (theme + '-actions.png'))
                chosen = []
                chapters = ChapterList(entries, chosen.append, row_style=hierarchy_row_style, current=1)
                view = toga.Box(children=[toga.Label('Contents', style=Pack(font_size=26, margin_bottom=16)),
                    toga.ScrollContainer(content=chapters.rows, horizontal=False, style=Pack(flex=1))],
                    style=Pack(direction=COLUMN, flex=1, margin=16))
                self.show_view(view, checkpoint=False, route='contents-qa', title='Book contents')
                await asyncio.sleep(.5)
                chapters.rows.children[0].disclosure.on_press()
                assert len(chapters.rows.children) == 4 and not chosen
                chapters.rows.children[0].disclosure.on_press()
                assert len(chapters.rows.children) == 7
                chapters.rows.children[1].title_button.on_press()
                assert chosen == [entries[1]]
                await asyncio.sleep(.4)
                await capture_window(self, output / (theme + '-epub.png'))
                owner = show_documentation(self, root, root / 'getting-started/connections.md')
                owner.show_browse()
                await asyncio.sleep(.7)
                folder = next(row for row in owner.rows.children if row.title_button.text == 'Getting started')
                before = owner.path
                folder.disclosure.on_press()
                assert owner.path == before
                folder = next(row for row in owner.rows.children if row.title_button.text == 'Getting started')
                folder.disclosure.on_press()
                await asyncio.sleep(.4)
                await capture_window(self, output / (theme + '-documentation.png'))
                folder = next(row for row in owner.rows.children if row.title_button.text == 'Getting started')
                folder.title_button.on_press()
                assert owner.path == root / 'getting-started/getting-started.md'
                pdf = PDFContents(NS(data=stream.getvalue()), on_page=chosen.append,
                    alive=lambda: True, row_style=hierarchy_row_style)
                self.show_view(toga.Box(children=[toga.Label('PDF navigation', style=Pack(font_size=26)), pdf],
                    style=Pack(direction=COLUMN, flex=1, margin=16)), checkpoint=False, route='pdf-qa', title='PDF contents')
                await pdf.toggle()
                assert len(pdf.tree.rows.children) == 3
                await asyncio.sleep(.6)
                await capture_window(self, output / (theme + '-pdf.png'))
                self.create_chosen_document('md', name=theme + '-Notes.md', content='# Travel notes\n\nPlaces to visit and things to remember.\n')
                await asyncio.sleep(.8)
                await capture_window(self, output / (theme + '-markdown.png'))
                report['samples'].append(theme)
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
            await capture_window(self, output / 'failure.png')
        (output / 'result.json').write_text(json.dumps(report, indent=2))
        print('SURFACE_HIERARCHY=' + json.dumps(report), flush=True)


def main():
    return Probe('Surface Hierarchy QA', 'io.github.ispaure.logisticssurfaceqa')
