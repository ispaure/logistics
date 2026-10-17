"""Actual Local/LocalCrypt vault controls, nested notes and adaptive presentation."""
import asyncio
from io import BytesIO
from features.rclone.mobile.storage_location import collection_path, CollectionFiles
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
        if label == 'local':
            await app.show_files(local_root=True)
            assert await app.browser_file_location(('Local files', 'Native Obsidian Vault'))
            browser = app.file_browser
        else:
            drawer = app.adaptive.browser('documents')
            assert await drawer.show_main_browser('LocalCrypt: Vault review', folder='Native Obsidian Vault', provider=provider)
            browser = drawer.browser
        assert browser.vault_button in browser.navigation_controls.children
        assert browser.vault_button.control_icon == 'obsidian'
        await asyncio.sleep(.2)
        await capture_window(app, output / (label + '-button.png'))
        owner = await browser.open_vault()
        assert owner is not None and owner.provider.root == provider.root
        if label == 'localcrypt':
            assert owner.provider is provider
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
        await capture_window(app, output / (label + '-note.png'))
        assert await owner.open_editor()
        assert 'Nested Markdown note' in app.provider_sessions().active.crypt_text.value
        app.close_crypt()
        owner.dispose()
        assert owner.path is None and not owner.rows.children
        for _ in range(50):
            text = await owner.web.evaluate_javascript('document.body ? document.body.textContent : ""')
            if 'Nested Markdown note' not in str(text):
                break
            await asyncio.sleep(.1)
        else:
            raise AssertionError('Retired vault retained its note preview')
    assert (ordinary.root / 'Native Obsidian Vault/Projects/Plan.md').read_bytes().startswith(b'# Native plan')
    for path in encrypted.root.rglob('*'):
        if path.is_file():
            assert b'Nested Markdown note' not in path.read_bytes()
