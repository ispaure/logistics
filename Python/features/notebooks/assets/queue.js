function send(action) {
  if (action.op !== 'document-location') {
    $('status').textContent = ['export', 'library', 'transfer', 'page'].includes(action.op) ? 'Opening…' : 'Saving…';
  }
  queue.push(action);
  pump()
}

function pump() {
  if (busy || !queue.length) return;
  let action = queue[0];
  const command = bridge + '?command=' + encodeURIComponent(JSON.stringify({
    sequence: seq + 1,
    action
  }));
  if (command.length > __MAX_COMMAND__) {
    queue = [];
    pendingInk = null;
    pendingErase = null;
    wholeErasePreview.clear();
    draw();
    $('status').textContent = 'Command too large. Draw a shorter stroke.';
    return
  }
  busy = true;
  seq++;
  __SEND_COMMAND__;
}
window.notebookUpdate = function(next, error) {
  if (continuousInk && active !== null) {
    deferredUpdate = () => window.notebookUpdate(next, error);
    return
  }
  if (queue[0]?.op === 'paste-image' && !error) imageSelection = next.images?.at(-1)?.id || null;
  state = next;
  pendingInk = null;
  pendingErase = null;
  wholeErasePreview.clear();
  busy = false;
  queue.shift();
  $('status').textContent = error || state.save_status || 'Saved on this device. Export a copy to share.';
  if (error) queue = [];
  render();
  pump()
};
window.notebookBrushColorUpdate = function(error) {
  busy = false;
  queue.shift();
  $('status').textContent = error || (queue.length ? 'Saving…' : state.save_status);
  pump();
};
// Mobile acknowledges durable strokes without resending/replaying the whole page.
window.notebookStrokeUpdate = function(stroke, status) {
  if(typeof inputTrace==='function')inputTrace(active!==null?'stroke-ack-deferred':'stroke-ack-applied');
  if (active !== null) {
    deferredUpdate = () => window.notebookStrokeUpdate(stroke, status);
    return
  }
  state.strokes.push(stroke);
  state.undo = true;
  state.redo = false;
  state.save_status = status;
  busy = false;
  queue.shift();
  pendingInk = null;
  $('undo').disabled = false;
  $('redo').disabled = true;
  $('status').textContent = queue.length ? 'Saving…' : status;
  // Interior strokes keep the existing incremental painting path. Only an
  // actual change in visible paper extent requires replaying the saved scene.
  if (strokeExpandsPaper(stroke)) resize();
  pump();
};
window.notebookInkUpdate = function(patch) {
  if (active !== null) {
    deferredUpdate = () => window.notebookInkUpdate(patch);
    return
  }
  const strokes = new Map(state.strokes.map(s => [s.id, s]));
  for (const stroke of patch.strokes) strokes.set(stroke.id, stroke);
  state.strokes = patch.order.map(id => strokes.get(id));
  if (patch.scene_order) state.scene_order = patch.scene_order;
  state.undo = patch.undo;
  state.redo = patch.redo;
  state.save_status = patch.save_status;
  pendingErase = null;
  wholeErasePreview.clear();
  pendingInk = null;
  busy = false;
  queue.shift();
  $('undo').disabled = !state.undo;
  $('redo').disabled = !state.redo;
  $('status').textContent = queue.length ? 'Saving…' : patch.save_status;
  if (paperView === 'move' && JSON.stringify(paperBounds()) !== JSON.stringify(displayedPaperBounds)) resize();
  else draw();
  pump()
};

// Hosts must drain native-bound ink before navigating away from an embedded canvas.
window.notebookIdle = () => !busy && !queue.length && active === null;
