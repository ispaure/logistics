"""Application composition of feature-facing presentation services."""


def rclone_host_ui(app):
    from features.rclone.mobile.host import MobileHostUI
    from logisticsmobile.control_icons import icon_button
    from logisticsmobile.browser_ui import FileBrowser as NativeBrowser
    from logisticsmobile.action_menu import FeatureCommands
    from logisticsmobile.provider_ui import private_label
    from logisticsmobile.folder_hub import visible_remotes
    from logisticsmobile.folder_hub import exclusions
    from logisticsmobile import pickers
    from logisticsmobile.resource_imports import ResourceImports
    from logisticsmobile.appearance import accessible_name
    from logisticsmobile.files_ui import local_read_available
    return MobileHostUI(icon_button=icon_button, NativeBrowser=NativeBrowser, FeatureCommands=lambda button, owner, *args, **kwargs: FeatureCommands(button, app, *args, **kwargs), private_label=private_label, visible_remotes=visible_remotes, exclusions=exclusions, pick_document=lambda owner: pickers.pick_document(app), ResourceImports=ResourceImports, export_file=lambda owner, selected: pickers.export_file(app, selected), accessible_name=accessible_name, local_read_available=lambda owner, **kwargs: local_read_available(app, **kwargs))
