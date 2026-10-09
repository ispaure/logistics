"""Lazy browser and page factories, independent of all media/Markdown features."""

from commonUtils.features import BrowserExtension, FileActivation, SelectionAction
from commonUtils.fileUtils import File
from commonUtils.text_files import is_text_path
from features.contributions import Feature, PageContribution, SettingsContribution
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
        pages=[PageContribution("Text Editor", "text_editor", create_page, order=35)],
        settings=[
            SettingsContribution(
                "Editor defaults",
                "text_editor",
                create_page,
                config_files=(Path(__file__).with_name("config.ini"),),
            )
        ],
    )
