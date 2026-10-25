"""Actual WebView input bridge, native ink encoding and on-device recovery."""
import asyncio
import json
from .web_checks import wait_for_text


async def exercise_notebooks(app):
    app.select_destination('notebooks')
    app.native_host.activate('notebooks')
    panel = app.notebook_panel
    await panel.new()
    await wait_for_text(panel.web, 'Notebook')
    result = await panel.web.evaluate_javascript("JSON.stringify({canvas:!!document.getElementById('paper'),pen:typeof PointerEvent,tools:document.getElementById('tool').options.length})")
    properties = json.loads(result)
    assert properties['canvas'] and properties['pen'] == 'function' and properties['tools'] == 8
    await panel.web.evaluate_javascript("send({op:'stroke',points:[[100,100,.2],[120,130,.8]],tool:12,color:6,width:3})")
    for _ in range(100):
        if panel.editor.notebook.page(0).strokes:
            break
        await asyncio.sleep(.1)
    assert len(panel.editor.notebook.page(0).strokes) == 1, 'Native WebView did not deliver editable ink'
    while panel.busy:
        await asyncio.sleep(.1)
    assert len(panel.repository.open(panel.key).page(0).strokes) == 1
    await panel.web.evaluate_javascript("send({op:'add-page'})")
    for _ in range(100):
        if len(panel.editor.notebook.pages) == 2 and not panel.busy:
            break
        await asyncio.sleep(.1)
    assert len(panel.editor.notebook.pages) == 2
    await panel.web.evaluate_javascript("document.getElementById('notebookName').value='Native notebook';document.getElementById('renameNotebook').click();document.getElementById('layerName').value='Details';document.getElementById('addLayer').click()")
    for _ in range(100):
        if panel.editor.notebook.name == 'Native notebook' and len(panel.editor.notebook.page(1).layers) == 2 and not panel.busy:
            break
        await asyncio.sleep(.1)
    assert panel.editor.notebook.name == 'Native notebook'
    assert panel.editor.notebook.page(1).layers[-1][1] == 'Details'
    recovered = panel.repository.open(panel.key)
    assert len(recovered.pages) == 2 and len(recovered.page(0).strokes) == 1
    exported = recovered.to_bytes()
    from features.notebooks.notebook import Notebook
    imported = Notebook.read(exported)
    assert not imported.page(0).warning and imported.page(0).strokes[0].tool == 12
    app.show_home()
