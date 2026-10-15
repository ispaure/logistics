"""ComicInfo native form values and sparse patches; validation stays in ComicInfo."""


def values(document):
    return {key: document.info.get_field(key) for key in document.info.FIELDS if key != 'PageCount'}


def patch(initial, edited):
    return {key: value for key, value in edited.items() if key in initial and value != initial[key]}


def batch_state(documents):
    from features.comics.edit_state import MetadataEditState
    state = MetadataEditState()
    snapshots = [values(document) for document in documents]
    if not snapshots:
        raise ValueError('Select at least one comic.')
    state.reset(snapshots, snapshots[0].keys())
    return state


def batch_form(documents, *, save, back, cancel, choices=None, width=None):
    """Explicit field selection distinguishes keeping a mixed field from clearing it."""
    import toga
    from toga.style import Pack
    from toga.style.pack import COLUMN
    state = batch_state(documents)
    inputs, switches, children, pickers = {}, {}, [], []
    busy = disposed = False
    status = toga.Label('Only checked fields are applied.\nChecked empty fields are cleared.')
    children.append(status)
    for key, entry in state.fields.items():
        switches[key] = toga.Switch('Apply ' + key, value=False, style=Pack(height=44))
        inputs[key] = toga.MultilineTextInput(value=entry.baseline,
            placeholder='Mixed values — keep unless checked' if entry.mixed else '', style=Pack(height=80))
        children.extend([switches[key], inputs[key]])
        if choices and choices.get(key):
            picker = suggestion_picker(key, inputs[key], choices[key], switch=switches[key])
            pickers.append(picker)
            children.append(picker)
    async def apply(widget, **kwargs):
        nonlocal busy
        if busy or disposed:
            return
        busy = True
        apply_button.enabled = False
        for field in inputs.values():
            field.readonly = True
        for picker in pickers:
            picker.enabled = False
        changes = {key: inputs[key].value for key in inputs if switches[key].value}
        for switch in switches.values():
            switch.enabled = False
        try:
            message = await save(changes)
            if not disposed:
                import textwrap
                status.text = textwrap.fill(message, 40)
        except Exception as error:
            if not disposed:
                status.text = 'Save failed; edits retained: ' + str(error)[:300]
        finally:
            busy = False
            apply_button.enabled = True
            for field in inputs.values():
                field.readonly = False
            for picker in pickers:
                picker.enabled = True
            for switch in switches.values():
                switch.enabled = True
    apply_button = toga.Button('Apply selected fields', on_press=apply, style=Pack(height=44))
    children.extend([apply_button,
        toga.Button('Cancel after current comic', on_press=cancel, style=Pack(height=44)),
        toga.Button('Back to library', on_press=back, style=Pack(height=44))])
    content_style = Pack(direction=COLUMN, margin=12)
    if width is not None:
        content_style.width = width
    view_style = Pack(flex=1)
    if width is not None:
        view_style.width = width + 24
    view = toga.ScrollContainer(horizontal=False, content=toga.Box(children=children,
        style=content_style), style=view_style)
    view.metadata_inputs, view.metadata_switches = inputs, switches
    view.metadata_apply, view.metadata_status = apply, status
    def dispose():
        nonlocal disposed
        disposed = True
        for field in inputs.values():
            field.value = ''
        for picker in pickers:
            picker.on_change = None
            picker.enabled = False
            picker.items = []
        inputs.clear()
        switches.clear()
        pickers.clear()
        state.fields.clear()
        status.text = ''
        view.content = toga.Label('Private batch closed. Reopen the folder to edit again.')
    view.dispose_metadata = dispose
    return view



def suggestion_picker(key, field, choices, *, switch=None):
    """Selecting a suggestion is explicit; constructing the form changes nothing."""
    import toga
    from toga.style import Pack
    from features.comics.catalog_values import LIST_FIELDS, split_values
    selector = toga.Selection(items=['Suggestions…', *choices], value='Suggestions…', style=Pack(height=44, width=250))
    def choose(widget, **kwargs):
        if not widget.enabled:
            return
        try:
            value = widget.value
        except IndexError:
            return
        if value == 'Suggestions…':
            return
        if key in LIST_FIELDS:
            field.value = ', '.join(dict.fromkeys([*split_values(field.value), value]))
        else:
            field.value = value
        if switch is not None:
            switch.value = True
        widget.value = 'Suggestions…'
    selector.on_change = choose
    return selector
