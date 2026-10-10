"""Sourcetree-style workspace sections and hierarchical reference paths."""
from commonUtils.ui import pyside as qt
from .chrome import action_icon


def populate_navigation(page, snapshot):
    tree = page.refs
    expanded = ({tree.topLevelItem(i).text(0): tree.topLevelItem(i).isExpanded()
                 for i in range(tree.topLevelItemCount())}
                if getattr(page, '_navigation_root', None) == snapshot.root else {})
    page._navigation_root = snapshot.root
    with qt.QSignalBlocker(tree):
        tree.clear()
        groups = {}
        for title in ('WORKSPACE','BRANCHES','TAGS','REMOTES','STASHES','SUBMODULES','SUBTREES'):
            item = qt.QTreeWidgetItem([title])
            item.setFlags(item.flags() & ~qt.Qt.ItemFlag.ItemIsSelectable)
            item.setSizeHint(0,qt.QSize(0,tree.fontMetrics().height()+18))
            item.setForeground(0,tree.palette().brush(qt.QPalette.ColorRole.PlaceholderText))
            item.setIcon(0,action_icon({'WORKSPACE':'folder','BRANCHES':'branch','TAGS':'commit','REMOTES':'remote','STASHES':'stash','SUBMODULES':'folder','SUBTREES':'branch'}[title]))
            font = item.font(0); font.setBold(True); item.setFont(0,font)
            tree.addTopLevelItem(item); item.setExpanded(expanded.get(title, title != 'TAGS'))
            groups[title] = item
        page.workspace_items = []
        for index, title in enumerate((f'File status ({len(snapshot.status.changes)})','History','Search')):
            item = qt.QTreeWidgetItem([title]); groups['WORKSPACE'].addChild(item)
            item.setData(0,qt.Qt.ItemDataRole.UserRole,('view',index,None))
            page.workspace_items.append(item)
        folders = {}
        def nested(group, name, value, current=False):
            parent = groups[group]
            parts = name.split('/')
            for depth in range(1,len(parts)):
                key = (group,'/'.join(parts[:depth]))
                if key not in folders:
                    folder = qt.QTreeWidgetItem([parts[depth-1]])
                    parent.addChild(folder); folder.setExpanded(True); folders[key] = folder
                parent = folders[key]
            item = qt.QTreeWidgetItem([('● ' if current else '') + parts[-1]])
            parent.addChild(item); item.setData(0,qt.Qt.ItemDataRole.UserRole,value)
            item.setToolTip(0,name)
            if current:
                font=item.font(0); font.setBold(True); item.setFont(0,font)
            return item
        for remote in snapshot.remotes:
            item = qt.QTreeWidgetItem([remote]); groups['REMOTES'].addChild(item); item.setExpanded(True)
            item.setData(0,qt.Qt.ItemDataRole.UserRole,('remote',remote,None))
            folders[('REMOTES',remote)] = item
        for ref in snapshot.refs:
            if ref.name.startswith('refs/heads/'):
                group,kind,name='BRANCHES','branch',ref.name[11:]
            elif ref.name.startswith('refs/remotes/'):
                group,kind,name='REMOTES','remote_branch',ref.name[13:]
            else: group,kind,name='TAGS','tag',ref.name[10:]
            item=nested(group,name,(kind,name,ref),ref.current)
            if ref.current and snapshot.status.upstream:
                item.setText(0,item.text(0)+f'  ↑{snapshot.status.ahead} ↓{snapshot.status.behind}')
        for ref,message in snapshot.stashes: nested('STASHES',message,('stash',ref,None))
        for path in snapshot.submodule_paths: nested('SUBMODULES',path,('submodule',path,None))
        for mapping in page.preferences.subtrees.get(str(snapshot.root),[]):
            if isinstance(mapping,dict) and isinstance(mapping.get('prefix'),str):
                nested('SUBTREES',mapping['prefix'],('subtree',mapping['prefix'],None))
