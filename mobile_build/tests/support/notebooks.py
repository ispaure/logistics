"""Isolated host fixtures for notebook storage and template selection."""
from unittest.mock import AsyncMock, patch

import toga

from features.notebooks.notebook import Notebook
from features.rclone.localcrypt.mobile.resources import CryptFiles
from mobile_build.tests.support.app import create_app
from mobile_build.tests.support.localcrypt import CreationClient


def _canvas(resource=None, **kwargs):
    view = toga.WebView(**kwargs)
    view.evaluate_javascript = AsyncMock(return_value=None)
    return view


def _dispose_notebook_views(app):
    for panel in tuple(getattr(app, '_notebook_views', {}).values()):
        panel.dispose()


def create_storage_notebook_app(case):
    """Use a synthetic canvas and a writable localcrypt provider."""
    # Register the canvas first so it stays patched during panel and app cleanup.
    case.enterContext(patch('services.documents.mobile_views.document_webview', side_effect=_canvas))
    app = create_app(case)
    case.addCleanup(_dispose_notebook_views, app)
    app.show_home()
    client = app.cloud_client = CreationClient()
    provider = CryptFiles(app.storage_root / 'LocalCryptFolders', client, 'Secret')
    return app, client, provider


def create_template_notebook_app(case):
    """Use the real panel setup with deterministic template choice and no JS."""
    case.enterContext(patch.object(toga.WebView, 'evaluate_javascript', new_callable=AsyncMock))
    case.enterContext(patch('features.notebooks.mobile.setup.choose_new_notebook',
                            new_callable=AsyncMock, side_effect=lambda *args, **kwargs: Notebook.new()))
    return create_app(case)


def create_notebook(case, *, private=True):
    """Create a notebook through the document picker in the storage fixture."""
    app = case.app
    run = app.loop.run_until_complete
    with patch.object(app, 'existing_crypt_locations', return_value={'LocalCrypt: Secret': case.provider}):
        with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value='rmdoc')):
            run(app.choose_document_type())
        picker = app.editor_picker()
        picker.creation_type.value = 'Remarkable Document (.rmdoc)'
        picker.save_as_name.value = 'Private sketch'
        run(picker.choose_creation_location())
    picker = app.editor_picker()
    picker.save_as_storage.value = 'LocalCrypt: Secret' if private else 'Local'
    run(picker.refresh_editor_browser())
    run(picker.confirm_editor_file())
    panel = app.notebook_panel
    case.assertIsNotNone(panel.editor, picker.save_as_status.value)
    panel.web.evaluate_javascript = AsyncMock(return_value=None)
    return panel


def draw_stroke(panel):
    panel.editor.apply(dict(op='stroke', points=[[20, 30, .4], [40, 50, .8]], tool=12, width=2))
