"""Native transfer progress and fallback controls for transfer review."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from datetime import datetime

import toga
from toga.style import Pack
from toga.style.pack import CENTER, COLUMN, ROW
from commonUtils.ui.native.appearance import accessible_name
from commonUtils.ui.native.forms import FittedLabel, fit_section, fit_text
from features.rclone.transfers.presentation import removal_counts


class NativeTransferFallback(toga.Box):
    def __init__(self, surface):
        super().__init__(style=Pack(direction=COLUMN, flex=1))
        self.surface = surface
        self.presentation = getattr(surface.host, 'presentation', None)
        self.title = FittedLabel('Transfers', style=Pack(font_size=22, font_weight='bold'))
        self.status = self.label('', size=15, muted=True)
        self.amount = self.label('', size=36, bold=True)
        self.metrics = self.label('', size=14)
        self.paths = self.label('', size=13, muted=True)
        self.stages = toga.Box(style=Pack(direction=ROW, gap=8))
        self.stage_labels = [self.label(name, size=12, bold=True, muted=True) for name in
                             ('Scan', 'Transfer', 'Verify')]
        self.stages.add(*self.stage_labels)
        for label in self.stage_labels:
            label.style.flex = 1
        self.progress_stage = None
        self.fields = toga.Box(style=Pack(direction=COLUMN, gap=12, margin_top=6))
        self.fact_names = ()
        self.fact_cells = []
        self.file_heading = self.label('Active files', size=17, bold=True)
        self.rows = toga.Box(style=Pack(direction=COLUMN, gap=9))
        self.buttons = toga.Box(style=Pack(direction=COLUMN, gap=8, margin=12))
        self.row_signature = self.button_signature = None
        self.scope = self.remote = None
        self._fitted_width = None
        self._layout_subscription = None
        self.progress = toga.ProgressBar(max=100, value=0, style=Pack(height=8, margin_bottom=4))
        self.summary = toga.Box(children=[self.title, self.status, self.metrics, self.paths],
                                style=Pack(direction=COLUMN, margin=16, gap=8))
        self.card = toga.Box(children=[self.summary], style=Pack(direction=COLUMN))
        if self.presentation:
            self.presentation.surface(self.card, radius=16, background='surface')
            self.presentation.surface(self.amount, radius=0, background='transparent', foreground='accent')
        self.history_signature = None
        self.history = toga.Box(style=Pack(direction=COLUMN, gap=8))
        self.body = toga.Box(children=[self.card, self.rows],
                             style=Pack(direction=COLUMN, gap=12, margin=12))
        content = toga.Box(children=[self.body], style=Pack(direction=COLUMN, align_items=CENTER))
        self.add(toga.ScrollContainer(content=content, horizontal=False, style=Pack(flex=1)), self.buttons)
        if self.presentation is not None and hasattr(surface.host, 'adaptive'):
            self._layout_subscription = self.presentation.register_layout(
                ('transfer', surface.token), self, NativeTransferFallback.reflow_surface)
            self.reflow_surface()

    def label(self, text, *, size=14, bold=False, muted=False):
        label = FittedLabel(text, style=Pack(font_size=size, font_weight='bold' if bold else 'normal'))
        if self.presentation and muted:
            self.presentation.surface(label, radius=0, background='transparent', foreground='muted')
        return label

    def button(self, title, action, enabled=True, **args):
        # Keep the revision shown by this particular native control. Replacing
        # a renderer never turns an old confirmation into fresh authorization.
        revision = self.surface.revision
        async def press(widget=None, **kwargs):
            if self.surface is not None:
                await self.surface.dispatch(action, dict(args, revision=str(revision)))
        control = toga.Button(title, enabled=enabled, on_press=press, style=Pack(height=48))
        if self.presentation:
            if action in ('approve', 'resume-download', 'downloads', 'start-review', 'background'):
                self.presentation.action_button(control)
            else:
                foreground = 'destructive' if action in ('stop', 'discard-download') else 'muted'
                self.presentation.surface(control, radius=10, background='transparent', foreground=foreground)
        return control

    def reflow_surface(self, frame=None):
        host = self.surface.host
        destination = host.native_host.state.destination
        width = (frame.content_width(destination, margin=0) if frame else
                 host.adaptive.content_width(destination, margin=0))
        self.reflow(width)

    def reflow(self, width):
        self._fitted_width = width
        content_width = min(640, max(1, width - 32))
        self.body.style.width = content_width
        in_scroll = self.buttons.parent is self.body
        side_by_side = in_scroll and content_width >= 460
        self.buttons.style.direction = ROW if side_by_side else COLUMN
        buttons = self.buttons.children
        button_width = max(24, content_width - 24)
        if side_by_side and buttons:
            button_width = max(24, (button_width - 8 * (len(buttons) - 1)) // len(buttons))
        for button in buttons:
            button.style.flex = 1 if side_by_side else 0
            fit_text(button, button_width)
        inner = max(24, content_width - 32)
        for control in self.summary.children:
            if isinstance(control, toga.Label):
                fit_text(control, inner)
        for label in self.stage_labels:
            fit_text(label, max(24, (inner - 16) // 3))
        for row in self.fields.children:
            cell_width = inner if len(row.children) == 1 else max(24, (inner - 12) // 2)
            for cell in row.children:
                fit_section(cell, cell_width)
        fit_section(self.rows, content_width)
        fit_section(self.history, content_width, fit=fit_transfer_control)

    def render(self, model):
        mode = model.get('mode')
        self.title.text = model.get('workspace') or 'Transfers'
        self.paths.text = 'Source: ' + model.get('source', '—') + '\nDestination: ' + model.get('destination', '—')
        buttons = []
        if mode == 'progress':
            phase = model.get('phase', 'idle')
            self.title.text = {'idle': 'Transfers', 'complete': 'Transfer complete',
                'failed': 'Transfer stopped', 'cancelled': 'Transfer cancelled',
                'conflict': 'Files changed during sync'}.get(phase, model.get('operation', 'Transfer'))
            self.status.text = progress_status(model)
            show_card = phase != 'idle' or self.status.text != 'No transfer is running.'
            if show_card and self.card.parent is None:
                self.body.insert(0, self.card)
            elif not show_card and self.card.parent is self.body:
                self.body.remove(self.card)
            self.render_progress_summary(model, phase)
            rows = tuple(str(row.get('name', '')) for row in model.get('active_files', ()))
            if model.get('busy'):
                buttons.append(('Stop transfer', 'stop', phase != 'stopping', {}))
            if phase != 'idle':
                buttons.append(('Continue browsing', 'background', True, {}))
            if buttons and self.buttons.parent is not self.body:
                if self.buttons.parent is self:
                    self.remove(self.buttons)
                self.body.insert(self.body.children.index(self.rows), self.buttons)
            elif not buttons and self.buttons.parent is not None:
                self.buttons.parent.remove(self.buttons)
            self.render_history(model)
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
            if mode == 'progress':
                if rows and self.file_heading.parent is None:
                    self.body.insert(self.body.children.index(self.rows), self.file_heading)
                elif not rows and self.file_heading.parent is self.body:
                    self.body.remove(self.file_heading)
            for text in rows:
                self.rows.add(self.label(text, size=14))
        # Progress redraws do not recreate controls. Review approval controls
        # are bound to the precise newly displayed revision.
        signature = (buttons, self.surface.revision if mode != 'progress' else None)
        if signature != self.button_signature:
            self.button_signature = signature
            self.buttons.clear()
            for title, action, enabled, args in buttons:
                self.buttons.add(self.button(title, action, enabled, **args))
        if self._fitted_width is not None:
            self.reflow(self._fitted_width)

    def render_progress_summary(self, model, phase):
        percentage = model.get('percentage')
        self.amount.text = f'{percentage:.0f}%' if percentage is not None else ''
        stage = {'scan': 0, 'transfer': 1, 'verify': 2, 'complete': 3}.get(phase)
        if self.progress_stage != stage:
            self.progress_stage = stage
            for index, (label, name) in enumerate(zip(self.stage_labels, ('Scan', 'Transfer', 'Verify'))):
                label.text = '✓ ' + name if stage is not None and index < stage else name
                if self.presentation:
                    self.presentation.surface(label, radius=0, background='transparent',
                                              foreground='accent' if index == stage else 'muted')
        show_bar = bool(model.get('busy')) or phase == 'complete'
        controls = [self.title, self.status]
        if stage is not None:
            controls.insert(0, self.stages)
        if percentage is not None and phase != 'idle':
            controls.append(self.amount)
        if show_bar:
            controls.append(self.progress)
        if phase != 'idle':
            controls.append(self.fields)
        if list(self.summary.children) != controls:
            # Keep shared controls attached across frequent progress updates.
            for control in tuple(self.summary.children):
                if control not in controls:
                    self.summary.remove(control)
            for index, control in enumerate(controls):
                if control.parent is None:
                    self.summary.insert(index, control)
        if show_bar:
            maximum = 100 if percentage is not None else None
            if self.progress.max != maximum:
                self.progress.stop()
                self.progress.max = maximum
                if maximum is None:
                    self.progress.start()
            if percentage is not None and self.progress.value != percentage:
                self.progress.value = percentage
        else:
            self.progress.stop()
        self.render_fields(progress_fields(model) if phase != 'idle' else ())

    def render_fields(self, rows):
        names = tuple(tuple(name for name, _ in fields) for fields in rows)
        if names != self.fact_names:
            self.fields.clear()
            self.fact_cells = []
            for fields in names:
                row = toga.Box(style=Pack(direction=ROW, gap=12))
                for name in fields:
                    label = self.label(name, size=12, muted=True)
                    value = self.label('', size=15, bold=True)
                    row.add(toga.Box(children=[label, value], style=Pack(direction=COLUMN, gap=3, flex=1)))
                    self.fact_cells.append(value)
                self.fields.add(row)
            self.fact_names = names
        for value, (_, detail) in zip(self.fact_cells, (field for row in rows for field in row)):
            if getattr(value, '_settings_source_text', value.text) != detail:
                value.text = detail

    def render_history(self, model):
        if model.get('busy'):
            if self.history.parent is self.body:
                self.body.remove(self.history)
            self.history.clear()
            self.history_signature = None
            return
        downloads, completed = model.get('downloads'), model.get('history')
        history_error = model.get('history_error')
        signature = (downloads, completed, model.get('downloads_notice'), model.get('history_notice'), history_error)
        if self.history_signature == signature:
            return
        self.history_signature = signature
        if self.history.parent is None:
            self.body.add(self.history)
        self.history.clear()
        self.history.add(self.label('Interrupted downloads', size=17, bold=True))
        if not downloads:
            self.history.add(self.label(model.get('downloads_notice', 'Loading interrupted downloads…'), muted=True))
        for job in downloads or ():
            title = self.label(job['name'], size=16, bold=True)
            progress = transfer_size(job['offset']) + ' of ' + transfer_size(job['size'])
            status = ('Folder · ' if job.get('folder') else '') + job['path'] + '\n' + progress
            status = self.label(status, size=13, muted=True)
            actions = dict(id=job['id'])
            resume = self.button('Resume', 'resume-download', **actions)
            discard = self.button('Discard…', 'discard-download', **actions)
            accessible_name(resume, 'Resume ' + job['name'])
            accessible_name(discard, 'Discard ' + job['name'])
            resume.style.flex = discard.style.flex = 1
            self.history.add(self.history_card(title, status,
                toga.Box(children=[resume, discard], style=Pack(direction=ROW, gap=8))))

        heading = self.label('Completed transfers', size=17, bold=True)
        heading.style.margin_top = 12
        self.history.add(heading)
        if history_error:
            self.history.add(self.label(history_error, muted=True))
        if not completed and not history_error:
            self.history.add(self.label(model.get('history_notice', 'Loading transfer history…'), muted=True))
        for entry in completed or ():
            date = datetime.fromtimestamp(entry['time'] / 1_000_000_000)
            title = entry['operation'].capitalize() + ' completed'
            status = entry['source'] + '\n→ ' + entry['destination'] + '\n' + date.strftime('%b %d, %Y %H:%M')
            if entry['bytes']:
                status += ' · ' + transfer_size(entry['bytes'])
            self.history.add(self.history_card(self.label(title, size=16, bold=True),
                                              self.label(status, size=13, muted=True)))
        if completed:
            self.history.add(self.button('Clear history…', 'clear-history'))

    def history_card(self, *controls):
        contents = toga.Box(children=controls, style=Pack(direction=COLUMN, gap=6, margin=12))
        card = toga.Box(children=[contents], style=Pack(direction=COLUMN))
        if self.presentation:
            self.presentation.surface(card, radius=12, background='surface')
        return card

    def clear_private_content(self):
        if self._layout_subscription is not None:
            self._layout_subscription.dispose()
            self._layout_subscription = None
        self.progress.stop()
        self.surface = None
        self.title.text = self.paths.text = self.status.text = self.metrics.text = self.amount.text = ''
        for value in self.fact_cells:
            value.text = ''
        self.render_fields(())
        for child in self.rows.children:
            if isinstance(child, toga.Label):
                child.text = ''
            elif isinstance(child, toga.Selection):
                child.items = []
        self.rows.clear()
        self.history.clear()
        self.history_signature = None
        for button in self.buttons.children:
            button.text = ''
        self.buttons.clear()
        self.row_signature = self.button_signature = None
        self.scope = self.remote = None


def fit_transfer_control(control, width):
    fit_text(control, width)
    if getattr(control, 'accessible_name', None):
        accessible_name(control, control.accessible_name)


def transfer_size(size):
    if size >= 1_000_000_000:
        return f'{size / 1_000_000_000:,.2f} GB'
    if size >= 1_000_000:
        return f'{size / 1_000_000:,.1f} MB'
    return f'{size:,} bytes'


def progress_status(model):
    phase = model.get('phase', 'idle')
    if phase == 'idle':
        return model.get('message') or 'No transfer is running.'
    if model.get('busy'):
        if model.get('retrying'):
            return f"Retrying · Attempt {model.get('attempt', 0)} of {model.get('max_attempts', 0)}"
        return {'scan': 'Checking the source and destination…', 'verify': 'Verifying the destination…',
                'stopping': 'Stopping transfer…'}.get(phase, model.get('status', 'Copying files…'))
    return model.get('message') or model.get('status') or 'No transfer is running.'


def progress_fields(model):
    done = transfer_size(model.get('done', 0))
    total = model.get('total', 0)
    files = model.get('files', 0)
    total_files = model.get('total_files', 0)
    amount = f'{done} / {transfer_size(total)}' if total else done
    count = f'{files:,} / {total_files:,}' if total_files else f'{files:,}'
    rows = [(('Files copied', count), ('Data copied', amount))]
    if model.get('elapsed'):
        minutes, seconds = divmod(model['elapsed'], 60)
        elapsed = [('Elapsed', f'{minutes}:{seconds:02d}')]
        if model.get('max_attempts'):
            elapsed.append(('Attempt', f"{model.get('attempt', 1)} / {model['max_attempts']}"))
        rows.append(tuple(elapsed))
    if model.get('checks') or model.get('listed'):
        rows.append((('Files found', f"{model.get('listed', 0):,}"),
                     ('Files compared', f"{model.get('checks', 0):,}")))
    if model.get('file_delete_attempts') is not None or model.get('folder_removal_attempts') is not None:
        rows.append((('Removal attempts', removal_counts(model)),))
    rows.extend(((('Source', model.get('source', '—')),), (('Destination', model.get('destination', '—')),)))
    return rows
