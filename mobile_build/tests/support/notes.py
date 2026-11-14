"""A fresh writable vault and dummy host for each Notes integration case."""

from unittest.mock import patch

import toga

from commonUtils.runtime.resources.local import LocalFiles
from mobile_build.tests.support.app import create_document_app


# Only the seed contents are shared. Each provider sees ordinary writable files
# with independent metadata, so rename, revision and indexing checks stay real.
VAULT_SEED = (
    ('.obsidian/private.md', '# Configuration'),
    ('Projects/Plan.MD', '# Plan\n\n**Nested note**'),
    ('Home.md', '# Home\n\n[Plan](Projects/Plan.MD)'),
    ('attachment.txt', 'Not a note'),
)


def set_up_vault(case):
    def webview(resource=None, *, inline_video=False, **options):
        return toga.WebView(**options)

    case.enterContext(patch('services.documents.mobile_views.document_webview', new=webview))
    case.app = create_document_app(case, storage_subdir='app')
    case.root = case.app.storage_root.parent
    case.vault = case.root / 'Vault'
    case.app.main_window._impl.dialog_responses['ErrorDialog'] = [None] * 10
    for name, content in VAULT_SEED:
        path = case.vault / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    case.provider = LocalFiles(case.root)


def run_async(case, awaitable):
    return case.app.loop.run_until_complete(awaitable)
