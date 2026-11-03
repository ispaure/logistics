"""Synthetic Notes Library performance and tab isolation on real native controls."""
import asyncio
import json
from pathlib import Path
from time import perf_counter
import traceback
from uuid import uuid4
from commonUtils.testing.stages import TestStage
from commonUtils.runtime.resources.local import LocalFiles
from mobile.app import LogisticsMobile
from mobile.obsidian import open_vault
from . import start_native_check
from .fixtures import capture_window

TEST_STAGE = TestStage.REGRESSION


class NotesAuditProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('notes-audit-' + uuid4().hex)
        super().startup()

    def on_running(self):
        start_native_check(self, type(self).probe)

    async def probe(self):
        report = dict(success=False)
        owner = heartbeat = None
        output = Path(self.paths.cache)
        evidence = output / 'viewer-layout'
        evidence.mkdir(exist_ok=True)
        try:
            root = output / ('synthetic-' + uuid4().hex)
            note = '# [[Tech]]\n\n' + ('A **bold** paragraph with an [example](Other.md).\n\n' * 1800)
            def seed():
                (root / '.obsidian').mkdir(parents=True)
                (root / 'Large.md').write_text(note)
                (root / 'Art.md').write_text('Synthetic one-line Art note.')
                (root / 'Projects').mkdir()
                (root / 'Projects/Tech.md').write_text('Synthetic nested Tech note.')
                body = ('Reading notes with a needleword in their content.\n' * 340)
                for i in range(1000):
                    (root / f'Note {i:04}.md').write_text(body)
            await asyncio.to_thread(seed)
            t = perf_counter()
            owner = await open_vault(self, LocalFiles(root), '', 'files')
            report['library_open_ms'] = (perf_counter() - t) * 1000
            if getattr(owner, 'tree_task', None) is not None:
                await owner.tree_task
            report['notes'] = 1003
            # Separate the former direct-link listing cost from target lookup,
            # and measure both cold and reused global wiki-name resolution.
            begin = perf_counter()
            await asyncio.to_thread(owner.library.provider.list, '')
            report['link_ancestor_listing_ms'] = (perf_counter() - begin) * 1000
            report['link_lookup_ms'] = {}
            for label, target in (('direct', 'Art'), ('global_cold', 'Tech'), ('global_warm', 'Tech')):
                begin = perf_counter()
                resolved = await asyncio.to_thread(owner.library.link, 'Welcome.md', target)
                report['link_lookup_ms'][label] = (perf_counter() - begin) * 1000
                assert resolved[0] == ('Art.md' if target == 'Art' else 'Projects/Tech.md')
            begin = perf_counter()
            assert await owner.open_note('Art', resolve_link=True)
            report['art_open_ms'] = (perf_counter() - begin) * 1000
            for _ in range(150):
                if await owner.web.evaluate_javascript(
                        '!!document.body && document.body.textContent.includes("Synthetic one-line Art note.")'):
                    break
                await asyncio.sleep(.05)
            else:
                raise AssertionError('The one-line Art note did not render')
            report['art_visible_ms'] = (perf_counter() - begin) * 1000
            report['body_bytes'] = 1000 * len(('Reading notes with a needleword in their content.\n' * 340).encode())
            report['tabs'] = dict(files=owner.files_content.parent is not None, calendar=owner.calendar_scroll.parent is not None)
            render_times, lag = [], []
            original_render = owner.render_tree
            def timed_render():
                begin = perf_counter()
                original_render()
                render_times.append((perf_counter() - begin) * 1000)
            owner.render_tree = timed_render
            async def tick():
                while True:
                    begin = perf_counter()
                    await asyncio.sleep(.02)
                    lag.append(max(0, (perf_counter() - begin - .02) * 1000))
            heartbeat = asyncio.create_task(tick())
            await asyncio.sleep(.05)
            lag.clear()
            begin = perf_counter()
            owner.search.value = 'needleword'
            await owner.search_task
            if getattr(owner, 'tree_task', None) is not None:
                await owner.tree_task
            await asyncio.sleep(.1)
            report['search'] = dict(elapsed_ms=(perf_counter()-begin)*1000, matches=len(owner.search_rows),
                max_event_loop_lag_ms=max(lag, default=0), renders=list(render_times), max_render_ms=max(render_times, default=0))
            await capture_window(self, evidence / 'search-results.png')
            owner.search.value = ''
            render_times.clear()
            lag.clear()
            begin = perf_counter()
            assert await owner.open_note('Large.md')
            report['read_open_ms'] = (perf_counter()-begin)*1000
            begin = perf_counter()
            assert await owner.open_editor()
            report['editor_open_ms'] = (perf_counter()-begin)*1000
            report['editor_max_event_loop_lag_ms'] = max(lag, default=0)
            for _ in range(150):
                if await owner.embedded.formatted.view.evaluate_javascript('!!window.markdownSnapshot'):
                    break
                await asyncio.sleep(.1)
            report['editor_ready_ms'] = (perf_counter()-begin)*1000
            await capture_window(self, evidence / 'large-editor.png')
            owner.dispose()
            owner = None
            await self.crypt_links(report)
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        finally:
            if heartbeat is not None:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
            if owner is not None:
                owner.dispose()
            (output / 'notes-audit-result.json').write_text(json.dumps(report, indent=2))

    async def crypt_links(self, report):
        from io import BytesIO
        from features.rclone.mobile.cloud import CloudClient
        from features.rclone.localcrypt.mobile.resources import encrypted_storage
        from features.notes_library.notes import NotesLibrary
        fixture = json.loads((Path(__file__).parent / 'localcrypt_fixture.json').read_text())
        client = self.cloud_client = CloudClient()
        client.request('import', package=fixture['package'], password='synthetic-resume-password',
                       package_name='Synthetic.zip', session_only=True)
        provider = encrypted_storage(self.private_root, client, 'Secret')
        library = NotesLibrary(provider)
        owner = None
        try:
            def seed():
                provider.mkdir('Projects')
                for path in ['Welcome.md', 'Art.md', 'Projects/Tech.md',
                             *(f'Note {index:04}.md' for index in range(512))]:
                    provider.create_file(path, BytesIO(b'Synthetic encrypted note.'))
            await asyncio.to_thread(seed)
            timings = report['localcrypt'] = dict(notes=515)
            begin = perf_counter()
            await asyncio.to_thread(provider.list, '')
            timings['former_ancestor_listing_ms'] = (perf_counter() - begin) * 1000
            for label, target in (('direct_ms', 'Art'), ('global_cold_ms', 'Tech'), ('global_warm_ms', 'Tech')):
                begin = perf_counter()
                await asyncio.to_thread(library.link, 'Welcome.md', target)
                timings[label] = (perf_counter() - begin) * 1000
            owner = await open_vault(self, provider, '', 'files')
            assert await owner.open_note('Welcome.md')
            begin = perf_counter()
            assert await owner.open_note('Art', resolve_link=True)
            for _ in range(150):
                if await owner.web.evaluate_javascript(
                        '!!document.body && document.body.textContent.includes("Synthetic encrypted note.")'):
                    break
                await asyncio.sleep(.05)
            else:
                raise AssertionError('Encrypted Art note did not render')
            timings['art_visible_ms'] = (perf_counter() - begin) * 1000
            for path in (self.private_root / 'workspace.json', self.private_root / 'recent-documents.json'):
                if path.exists():
                    assert b'Art.md' not in path.read_bytes() and b'Welcome.md' not in path.read_bytes()
            timings['no_plaintext_note_history'] = True
            self.clear_private_catalog()
            assert owner.path is None
            assert not owner.history and not owner.positions and not owner.library._link_folders
            timings['lock_cleared_names_and_history'] = True
        finally:
            if owner is not None:
                owner.dispose()
            library.close()
            provider.close()
            client.clear()


def main():
    return NotesAuditProbe('Notes Audit QA', 'io.github.ispaure.logisticsnotesauditqa')
