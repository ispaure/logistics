"""Actual Local/LocalCrypt vault controls, nested notes and adaptive presentation."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from io import BytesIO
from services.documents.locations import collection_path, CollectionFiles
from .fixtures import capture_window


async def exercise_obsidian(app, encrypted):
    collection_path(app.private_root).mkdir(parents=True, exist_ok=True)
    ordinary = CollectionFiles(app.private_root)
    output = app.private_root / 'obsidian-review'
    output.mkdir(exist_ok=True)
    for label, provider in [('local', ordinary), ('localcrypt', encrypted)]:
        for folder in ('Native Obsidian Vault', 'Native Obsidian Vault/.obsidian', 'Native Obsidian Vault/Projects'):
            provider.mkdir(folder)
        for path, data in [('Home.md', b'# Native vault\n\n[Plan](Projects/Plan.md)'),
                           ('Projects/Plan.md', b'# Native plan\n\n**Nested Markdown note**'),
                           ('.obsidian/hidden.md', b'# Not a note'), ('attachment.txt', b'Not Markdown')]:
            provider.create_file('Native Obsidian Vault/' + path, BytesIO(data))
        from unittest.mock import patch
        from contextlib import nullcontext
        entry = dict(source='Local' if label == 'local' else 'LocalCrypt',
            kind='local' if label == 'local' else 'crypt',
            value='Native Obsidian Vault' if label == 'local' else encrypted.remote,
            name='Native Notes Library', copies=[])
        # This fixture's crypt vault is a selected subfolder inside the native
        # encrypted root. Production mapped roots use the same provider/scope.
        scope = (patch('mobile.notes_actions.resolve_source', return_value=(provider, 'Native Obsidian Vault'))
                 if label == 'localcrypt' else nullcontext())
        with scope:
            app.show_picker_folder(entry)
            await app._notes_offer_task
        button = next(button for button, _ in app.folder_action_controls if button.text == 'Open as Notes Library')
        assert button.parent is not None
        await capture_window(app, output / (label + '-button.png'))
        await button.on_press()
        owner = app.vault_browser
        assert app.native_host.state.destination == 'files'
        assert owner.destination == 'files'
        assert owner.session.provider == 'notes-library'
        assert owner is not None and owner.provider.root == provider.root
        if label == 'localcrypt':
            # Each Notes Library now owns an independently closable grant.
            assert owner.provider is not provider
            assert owner.provider.client is provider.client
            assert owner.provider.identity == provider.identity
            assert owner.provider.storage_namespace == provider.storage_namespace
            assert not owner.provider.closed and not provider.closed
        assert {row.children[-1].vault_path for row in owner.rows.children} == {
            'Native Obsidian Vault/Projects', 'Native Obsidian Vault/Home.md'}
        await owner.toggle_folder('Native Obsidian Vault/Projects')
        assert len(owner.rows.children) == 3
        assert await owner.open_note('Native Obsidian Vault/Projects/Plan.md')
        for _ in range(150):
            text = await owner.web.evaluate_javascript('document.body ? document.body.textContent : ""')
            if 'Nested Markdown note' in str(text):
                break
            await asyncio.sleep(.1)
        else:
            raise AssertionError('Native vault Markdown did not render')
        owner.reflow(app.adaptive.content_width(owner.destination, margin=0))
        if owner.sidebar.expanded:
            assert list(owner.sidebar.view.children) == [owner.tree, owner.article]
        else:
            owner.menu.on_press()
            assert list(owner.sidebar.view.children) == [owner.tree]
        await capture_window(app, output / (label + '-tree.png'))
        owner.sidebar.show_detail()
        await asyncio.sleep(.3)
        await capture_window(app, output / (label + '-note.png'))
        assert await owner.open_editor()
        assert 'Nested Markdown note' in app.provider_sessions().active.crypt_text.value
        app.close_crypt()
        # WKWebView may defer an offscreen replacement document. Close the
        # visible Notes Library so the rendered cleanup proof can complete.
        owner.present()
        await asyncio.sleep(.2)
        # Compact navigation retires a hidden article too. Its live DOM must
        # clear even when WKWebView defers an offscreen replacement load.
        owner.sidebar.show_sidebar()
        owner.dispose()
        assert owner.path is None and not owner.rows.children
        if label == 'localcrypt':
            assert owner.provider.closed and not provider.closed
        if hasattr(owner.web, 'private_closed'):
            # Android deliberately destroys a private WebView; evaluating JS on
            # a destroyed view cannot produce a callback.
            assert owner.web.private_closed
            if owner.web.factory.WebView.__module__.startswith('toga_iOS.'):
                from .web_checks import wait_for_text
                await wait_for_text(owner.web, '', absent='Nested Markdown note')
        else:
            from .web_checks import wait_for_text
            await wait_for_text(owner.web, 'Document closed.', absent='Nested Markdown note')
    assert (ordinary.root / 'Native Obsidian Vault/Projects/Plan.md').read_bytes().startswith(b'# Native plan')
    for path in encrypted.root.rglob('*'):
        if path.is_file():
            assert b'Nested Markdown note' not in path.read_bytes()
