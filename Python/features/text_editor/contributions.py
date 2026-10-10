"""Lazy browser and page factories, independent of all media/Markdown features."""

from commonUtils.features import BrowserExtension, FileActivation, SelectionAction
from commonUtils.fileUtils import File
from commonUtils.persistence.text import is_text_path
from features.contributions import Feature, SettingsContribution, DocumentLauncherContribution
from pathlib import Path


def create_page(parent=None):
    from .page import TextEditorPage

    return TextEditorPage(parent)


def create_controller(host):
    from .service import BrowserController

    return BrowserController(host)


def open_text(context):
    return [context.controller.open(path) for path in context.paths]


def force_text(context):
    return [context.controller.open(path, force=True) for path in context.paths]


def text_selection(context):
    return all(is_text_path(item.path) for item in context.selection)


def activate_text(context):
    from commonUtils.fileTypes.markdownType import MarkdownFile
    from commonUtils.fileTypes.txtType import TXTFile

    item = context.item
    return (
        not isinstance(item, MarkdownFile)
        and (type(item) is File or isinstance(item, TXTFile))
        and is_text_path(context.path)
    )


def register():
    return Feature(
        id="text_editor",
        label="Text Editor",
        document_launchers=[DocumentLauncherContribution("text", "Text Editor", launch, "text", 10, new_document)],
        browser=BrowserExtension(
            actions=(
                SelectionAction(
                    "open",
                    "Open in Text Editor",
                    File,
                    open_text,
                    is_available=text_selection,
                    order=5,
                ),
                SelectionAction(
                    "force", "Force Open as Text…", File, force_text, order=90
                ),
            ),
            activation=(FileActivation(File, open_text, is_available=activate_text),),
            create_controller=create_controller,
        ),
        settings=[
            SettingsContribution(
                "Editor defaults",
                "text_editor",
                create_page,
                config_files=(Path(__file__).with_name("config.ini"),),
            )
        ],
    )


def _service(parent):
    from .service import EditorService
    service = getattr(parent, '_text_editor_service', None)
    if service is None:
        service = parent._text_editor_service = EditorService(parent)
    return service


def launch(parent):
    from commonUtils.ui import pyside as qt
    path, _ = qt.QFileDialog.getOpenFileName(parent, 'Open text file', '', 'Text files (*.txt *.log *.py *.json *.ini *.csv);;All files (*)')
    if path:
        return _service(parent).open(path)


def new_document(parent):
    from .window import EditorWindow
    from commonUtils.ui.document_host import show_document
    window = EditorWindow(service=_service(parent))
    show_document(window)
    return window
