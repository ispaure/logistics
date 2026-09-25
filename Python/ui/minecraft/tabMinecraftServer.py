from typing import List

from commonUtils.ui import pyside

from features.minecraft import detection, server


def display_servers(dialog_obj, server_type: server.MinecraftServerType):
    """
    Display one row per Minecraft server with its actions.
    """

    # Server root path
    server_path = detection.get_server_root_path(server_type)

    # Get servers
    server_lst: List[server.MinecraftServer] = server.get_minecraft_server_lst(server_path)

    # Layout sizing
    row_height = 36
    header_height = 36
    extra_padding = 20
    scroll_height = max(header_height + len(server_lst) * row_height + extra_padding, 80)

    # Scroll area + grid
    widget_content, grid_layout = pyside.create_scroll_area_grid(
        target=dialog_obj,
        rect=pyside.QRect(0, 0, 700, 450),
        rect_content=pyside.create_size(695, scroll_height)
    )

    # Column definitions:
    # (header text, button text function, callback function, enabled check)
    columns = [
        ("Server", lambda s: s.name, lambda s: s.launch_server, lambda s: s.is_launchable()),
        ("Browse to Folder", lambda s: "Browse Folder", lambda s: s.open_dir, lambda s: s.can_open_dir()),
        ("Open Wiki", lambda s: "Open Wiki", lambda s: s.open_wiki, lambda s: s.can_open_wiki()),
        ("Server.Properties", lambda s: "server.properties", lambda s: s.edit_properties, lambda s: s.can_edit_props()),
        ("Do Thing 2", lambda s: "Do Thing 2", lambda s: s.do_thing_2, lambda s: True),
    ]

    # # Optional header row (kept for clarity)
    # for col, (header_text, _, _, _) in enumerate(columns):
    #     header_btn = pyside.button(
    #         text=header_text,
    #         target=widget_content,
    #         rect=pyside.QRect(0, 0, 130, 30),
    #         fn=None
    #     )
    #     header_btn.setEnabled(False)
    #     grid_layout.addWidget(header_btn, 0, col)

    # Server rows
    for row, mc_server in enumerate(server_lst, start=1):
        for col, (_, text_fn, callback_fn, enabled_fn) in enumerate(columns):
            btn = pyside.button(
                text=text_fn(mc_server),
                target=widget_content,
                rect=pyside.QRect(0, 0, 130, 30),
                fn=callback_fn(mc_server)
            )

            # Enable / disable (grey out)
            btn.setEnabled(enabled_fn(mc_server))

            grid_layout.addWidget(btn, row, col)
