"""Native transfer controls when the optional formatted renderer cannot load."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from features.rclone.transfers.presentation import removal_counts


class NativeTransferFallback(toga.Box):
    def __init__(self, surface):
        super().__init__(style=Pack(direction=COLUMN, flex=1, margin=12))
        self.surface = surface
        self.title = toga.Label('Transfers', style=Pack(font_size=22))
        self.paths = toga.Label('')
        self.status = toga.Label('')
        self.metrics = toga.Label('')
        self.rows = toga.Box(style=Pack(direction=COLUMN))
        self.buttons = toga.Box(style=Pack(direction=COLUMN))
        self.row_signature = self.button_signature = None
        self.scope = self.remote = None
        body = toga.Box(children=[self.title, toga.Label('Simplified transfer view'),
            self.paths, self.status, self.metrics, self.rows], style=Pack(direction=COLUMN))
        self.add(toga.ScrollContainer(content=body, horizontal=False, style=Pack(flex=1)), self.buttons)

    def button(self, title, action, enabled=True, **args):
        # Keep the revision shown by this particular native control. Replacing
        # a renderer never turns an old confirmation into fresh authorization.
        revision = self.surface.revision
        async def press(widget=None, **kwargs):
            if self.surface is not None:
                await self.surface.dispatch(action, dict(args, revision=str(revision)))
        return toga.Button(title, enabled=enabled, on_press=press, style=Pack(height=48))

    def render(self, model):
        mode = model.get('mode')
        self.title.text = model.get('workspace') or 'Transfers'
        self.paths.text = 'Source: ' + model.get('source', '—') + '\nDestination: ' + model.get('destination', '—')
        buttons = []
        if mode == 'progress':
            phase = model.get('phase', 'idle')
            self.status.text = phase.capitalize() + '\n' + (model.get('message') or model.get('status', ''))
            percentage = model.get('percentage')
            self.metrics.text = ((f'{percentage:.0f}%\n' if percentage is not None else '')
                + f"Files: {model.get('files', 0):,} / {model.get('total_files', 0):,}\n"
                + f"Data: {model.get('done', 0) / 1_000_000:,.2f} / {model.get('total', 0) / 1_000_000:,.2f} MB\n"
                + f"Checked: {model.get('checks', 0):,} · Listed: {model.get('listed', 0):,}")
            if phase != 'idle':
                self.metrics.text += '\nRemoval attempts: ' + removal_counts(model)
            rows = tuple(str(row.get('name', '')) for row in model.get('active_files', ()))
            if model.get('busy'):
                buttons.append(('Stop transfer', 'stop', phase != 'stopping', {}))
            buttons.append(('Continue browsing', 'background', True, {}))
        elif mode == 'review':
            self.status.text = model.get('notice', '')
            counts = model.get('counts', {})
            self.metrics.text = (' · '.join(f'{name.capitalize()}: {counts.get(name, 0):,}'
                for name in ('add', 'replace', 'delete', 'cleanup'))
                + '\nDestination replacements and deletions have no undo.'
                + f"\nPage {model.get('page', 0) + 1} · {model.get('total', 0):,} matching changes")
            rows = tuple(f'{kind.capitalize()}: {path}' for kind, path in model.get('rows', ()))
            page, size, total = model.get('page', 0), model.get('page_size', 30), model.get('total', 0)
            buttons.extend([('Previous changes', 'previous', page > 0, {}),
                ('Next changes', 'next', (page + 1) * size < total, {})])
            if model.get('query') or model.get('filter', 'all') != 'all':
                buttons.append(('Show all changes', 'filter', True, dict(kind='all', query='')))
            buttons.append(('Approve ' + model.get('operation', 'transfer'), 'approve', bool(model.get('can_confirm')), {}))
            if model.get('can_early') and not model.get('complete'):
                self.metrics.text += '\nSkipping may replace or delete more files.'
                buttons.append(('Skip preview and start', 'early', True, {}))
            buttons.append(('Cancel review', 'background', True, {}))
        else:
            self.status.text = 'Review additions, replacements and deletions before anything changes.'
            self.metrics.text = 'The current destination is shown above.'
            rows = ()
            if self.scope is None:
                self.rows.clear()
                remotes = model.get('remotes', ())
                specific = model.get('destination') != model.get('workspace', '') + ':'
                self.scope = toga.Switch('As a subfolder', value=specific)
                self.remote = toga.Selection(items=remotes)
                selected = model.get('destination', '').split(':', 1)[0]
                if specific and selected in remotes:
                    self.remote.value = selected
                async def scope_changed(widget=None, **kwargs):
                    if self.surface is not None:
                        await self.surface.dispatch('scope', dict(specific='1' if self.scope.value else '0', remote=self.remote.value or ''))
                self.scope.on_change = self.remote.on_change = scope_changed
                self.rows.add(self.scope, toga.Label('Remote destination'), self.remote)
            buttons.extend([('Review Push', 'start-review', True, {}),
                ('Transfer settings', 'settings', True, {}), ('Cancel', 'background', True, {})])
        if mode in ('progress', 'review') and rows != self.row_signature:
            self.row_signature = rows
            self.rows.clear()
            for text in rows:
                self.rows.add(toga.Label(text))
        # Progress redraws do not recreate controls. Review approval controls
        # are bound to the precise newly displayed revision.
        signature = (buttons, self.surface.revision if mode != 'progress' else None)
        if signature != self.button_signature:
            self.button_signature = signature
            self.buttons.clear()
            for title, action, enabled, args in buttons:
                self.buttons.add(self.button(title, action, enabled, **args))

    def clear_private_content(self):
        self.surface = None
        self.title.text = self.paths.text = self.status.text = self.metrics.text = ''
        for child in self.rows.children:
            if isinstance(child, toga.Label):
                child.text = ''
            elif isinstance(child, toga.Selection):
                child.items = []
        self.rows.clear()
        self.buttons.clear()
        self.row_signature = self.button_signature = None
        self.scope = self.remote = None
