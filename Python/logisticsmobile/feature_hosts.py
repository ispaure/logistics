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
    from logisticsmobile.folder_hub_style import source_actions
    from logisticsmobile.files_ui import local_read_available
    from logisticsmobile.settings_ui import ConnectionSettingsPage, connection_group, connection_field, connection_note, connection_heading, connection_disclosure
    return MobileHostUI(icon_button=icon_button, NativeBrowser=NativeBrowser, FeatureCommands=lambda button, owner, *args, **kwargs: FeatureCommands(button, app, *args, **kwargs), private_label=private_label, visible_remotes=visible_remotes, exclusions=exclusions, pick_document=lambda owner: pickers.pick_document(app), ResourceImports=ResourceImports, export_file=lambda owner, selected: pickers.export_file(app, selected), accessible_name=accessible_name, local_read_available=lambda owner, **kwargs: local_read_available(app, **kwargs), refresh_folder_source_actions=lambda: source_actions(app), settings_page=lambda *args: ConnectionSettingsPage(app, *args), settings_group=connection_group, settings_field=connection_field, settings_note=connection_note, settings_heading=connection_heading, settings_disclosure=connection_disclosure)


def mobile_presentation(app):
    from services.mobile_presentation import MobilePresentation
    from logisticsmobile.control_icons import icon_button
    from logisticsmobile.control_icons import apply_icon
    from logisticsmobile.appearance import action_button
    from logisticsmobile.action_menu import ActionMenu
    from logisticsmobile.appearance import surface
    from logisticsmobile.appearance import apple_color
    from logisticsmobile.workspace_navigation import menu_button
    from logisticsmobile.pickers import export_document
    from logisticsmobile.preview import markdown_preview
    from logisticsmobile.palette import css_variables
    from logisticsmobile.recycled_file_list import summary_list
    return MobilePresentation(icon_button=icon_button, apply_icon=apply_icon, action_button=action_button, ActionMenu=ActionMenu, surface=surface, apple_color=apple_color, menu_button=menu_button, export_document=lambda owner, *args, **kwargs: export_document(app, *args, **kwargs), markdown_preview=markdown_preview, css_variables=css_variables, summary_list=summary_list)
