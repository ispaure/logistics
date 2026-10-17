"""Lazy browser and page factories, independent of all media/Markdown features."""

from commonUtils.ui.features import BrowserExtension, FileActivation, SelectionAction
from commonUtils.filesystem.files import File
from commonUtils.persistence.text import is_text_path
from features.contributions import Feature, SettingsContribution, DocumentLauncherContribution
from pathlib import Path


def create_page(parent=None):
    from features.text_editor.ui.page import TextEditorPage

    return TextEditorPage(parent)


def create_controller(host):
    from features.text_editor.ui.service import BrowserController

    return BrowserController(host)


def open_text(context):
    return [context.controller.open(path) for path in context.paths]


def force_text(context):
    return [context.controller.open(path, force=True) for path in context.paths]


def text_selection(context):
    return all(is_text_path(item.path) for item in context.selection)


def activate_text(context):
    from commonUtils.formats.markdownType import MarkdownFile
    from commonUtils.formats.txtType import TXTFile

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
        document_launchers=[DocumentLauncherContribution("text", "Text Editor", launch, "text", 10, new_document, "Edit plain text and code files.")],
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
                config_files=(Path(__file__).with_name("config.ini"),),
            )
        ],
    )


def _service(parent):
    from features.text_editor.ui.service import EditorService
    parent = getattr(parent, 'document_service_owner', parent)
    service = getattr(parent, '_text_editor_service', None)
    if service is None:
        service = parent._text_editor_service = EditorService(parent)
    return service


def launch(parent):
    from services.documents.ui.editors import choose_editor_resource, open_editor_choice
    choice = choose_editor_resource(parent, 'open')
    if choice:
        if getattr(choice.provider, 'private', False):
            return open_editor_choice(choice, parent)
        path = choice.provider.root / choice.path
        choice.close()
        return _service(parent).open(path)


def new_document(parent):
    from features.text_editor.ui.window import EditorWindow
    from commonUtils.ui.document_host import show_document
    window = EditorWindow(service=_service(parent))
    show_document(window)
    return window
