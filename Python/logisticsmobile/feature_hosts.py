"""Application composition of feature-facing presentation services."""


def rclone_host_ui():
    from features.rclone.mobile.host import MobileHostUI
    from logisticsmobile.control_icons import icon_button
    from logisticsmobile.browser_ui import FileBrowser as NativeBrowser
    from logisticsmobile.action_menu import FeatureCommands
    from logisticsmobile.provider_ui import private_label
    from logisticsmobile.folder_hub import visible_remotes
    from logisticsmobile.folder_hub import exclusions
    from logisticsmobile.pickers import pick_document
    from logisticsmobile.resource_imports import ResourceImports
    from logisticsmobile.pickers import export_file
    from logisticsmobile.appearance import accessible_name
    from logisticsmobile.files_ui import local_read_available
    return MobileHostUI(icon_button=icon_button, NativeBrowser=NativeBrowser, FeatureCommands=FeatureCommands, private_label=private_label, visible_remotes=visible_remotes, exclusions=exclusions, pick_document=pick_document, ResourceImports=ResourceImports, export_file=export_file, accessible_name=accessible_name, local_read_available=local_read_available)
