"""Desktop conversation menu assembly; actions and session state stay on the page."""
from commonUtils.ui import pyside as qt


def build_menus(page, layout):
    page.menu_bar = qt.QMenuBar()
    page.menu_bar.setNativeMenuBar(False)
    layout.insertWidget(0, page.menu_bar)
    file = page.menu_bar.addMenu('File')
    page.idle_menu_actions = [file.addAction('New conversation', page.conversations.new_conversation),
                              file.addAction('New folder…', page.conversations.new_folder)]
    file.addSeparator()
    for action in (page.rename_button, page.move_button, page.export_button, page.delete_button):
        file.addAction(action)
    edit = page.menu_bar.addMenu('Edit')
    page.draft_actions = []
    for label, callback in [('Undo draft', page.composer.undo), ('Redo draft', page.composer.redo),
                            ('Cut draft selection', page.composer.cut), ('Copy draft selection', page.composer.copy),
                            ('Paste into draft', page.composer.paste), ('Select draft', page.composer.selectAll)]:
        page.draft_actions.append(edit.addAction(label, callback))
    chat = page.menu_bar.addMenu('Conversation')
    chat.addAction(page.pin_action)
    chat.addAction(page.fork_action)
    view = page.menu_bar.addMenu('View')
    page.idle_menu_actions.append(view.addAction('Refresh conversations', page.refresh))
    view.addAction('Find conversations', page.search.setFocus)
    sidebar = view.addAction('Conversation sidebar')
    sidebar.setCheckable(True)
    sidebar.setChecked(True)
    sidebar.toggled.connect(page.sidebar.setVisible)
    generation = view.addAction('Generation settings')
    generation.setCheckable(True)
    generation.toggled.connect(page.settings_toggle.setChecked)
    page.settings_toggle.toggled.connect(generation.setChecked)
    server = page.menu_bar.addMenu('Server')
    page.idle_menu_actions.extend([server.addAction('Manage profiles…', page.edit_profiles),
                                  server.addAction('Test connection / Refresh models', page.refresh_models)])
