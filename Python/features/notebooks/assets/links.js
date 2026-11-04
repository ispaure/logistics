// Link gestures own no ink commands. Only completed taps can navigate.
let linkGesture = null, pendingLinkJump = null, linkReturn = null, linkTimer = null;
const undoPageJump = document.createElement('button');
undoPageJump.id = 'undoPageJump';
undoPageJump.type = 'button';
undoPageJump.textContent = 'Undo page jump';
undoPageJump.hidden = true;
undoPageJump.style.cssText = 'position:fixed;bottom:20px;left:50%;transform:translateX(-50%);z-index:1000;min-height:44px;padding:8px 20px';
document.body.append(undoPageJump);
function clearLinkReturn() {
  clearTimeout(linkTimer); linkReturn = null; undoPageJump.hidden = true
}
undoPageJump.onclick = () => {
  if (busy || active !== null || linkReturn === null) return;
  const index = linkReturn; clearLinkReturn(); send({op: 'page', index})
};
function notebookLinkAt(e) {
  const [x, y] = coord(e), b = state.pdf_paper || {x: 0, y: 0, width: state.width, height: state.height};
  const px = (x-b.x)/b.width, py = (y-b.y)/b.height;
  return (state.links || []).find(link => {
    const [l,t,r,b] = link.rect; return px >= l && px <= r && py >= t && py <= b
  })
}
const linkDown = canvas.onpointerdown, linkMove = canvas.onpointermove,
  linkUp = canvas.onpointerup, linkCancel = canvas.onpointercancel;
document.addEventListener('pointerdown', e => {
  if (linkGesture && e.pointerId !== linkGesture.id) linkGesture.cancelled = true
}, true);
canvas.onpointerdown = e => {
  if (typeof mode !== 'undefined' && mode === 'select') return linkDown(e);
  const mobile = document.body.classList.contains('notebook-mobile');
  const mac = /Mac|iPhone|iPad/.test(navigator.platform);
  const allowed = mobile ? e.pointerType === 'touch' && !penTouchBlocked() :
    e.pointerType === 'mouse' && e.button === 0 && (mac ? e.metaKey : e.ctrlKey);
  const link = allowed && !busy && active === null && !pan && !state.password_required && notebookLinkAt(e);
  if (!link) return linkDown(e);
  linkGesture = {id: e.pointerId, x: e.clientX, y: e.clientY, time: performance.now(),
    link, index: state.index, moved: false, cancelled: false};
  beginPan(e)
};
canvas.onpointermove = e => {
  if (linkGesture?.id === e.pointerId && Math.hypot(e.clientX-linkGesture.x, e.clientY-linkGesture.y) > 8)
    linkGesture.moved = true;
  if (linkGesture?.id === e.pointerId) {
    if (pan?.id === e.pointerId && !linkGesture.cancelled) {
      if (!pan.paging) $('viewport').scrollLeft += pan.x-e.clientX;
      $('viewport').scrollTop += pan.y-e.clientY;
      pan.x = e.clientX; pan.y = e.clientY
    }
    e.preventDefault(); return
  }
  return linkMove(e)
};
canvas.onpointerup = e => {
  const gesture = linkGesture;
  if (!gesture || gesture.id !== e.pointerId) return linkUp(e);
  linkGesture = null;
  const paging = pan?.paging, owned = pan?.id === e.pointerId && !pan.cancelled;
  pan = null;
  if (!owned || gesture.cancelled || gesture.moved || Math.hypot(e.clientX-gesture.x, e.clientY-gesture.y) > 8 ||
      performance.now()-gesture.time > 600 || busy || state.index !== gesture.index) {
    const dx = e.clientX-gesture.x, dy = e.clientY-gesture.y;
    if (owned && !gesture.cancelled && paging && !busy && state.index === gesture.index &&
        performance.now()-gesture.time < 900 && Math.abs(dx) >= 48 && Math.abs(dx) > Math.abs(dy)*1.5) {
      const index = state.index+(dx < 0 ? 1 : -1);
      if (index >= 0 && index < state.count) send({op: 'page', index})
    }
    return
  }
  e.preventDefault();
  if (gesture.link.index !== state.index) {
    clearLinkReturn();
    pendingLinkJump = {from: state.index, to: gesture.link.index};
    send({op: 'page', index: gesture.link.index})
  }
};
function cancelLink(e) {
  if (linkGesture?.id === e.pointerId) {linkGesture = null; pan = null; return}
  return linkCancel(e)
}
canvas.onpointercancel = cancelLink;
canvas.onlostpointercapture = cancelLink;
const linkUpdate = window.notebookUpdate;
window.notebookUpdate = (next, error) => {
  const completed = queue[0];
  if (next.index !== state.index) clearLinkReturn();
  linkUpdate(next, error);
  if (pendingLinkJump && completed?.op === 'page') {
    if (!error && next.index === pendingLinkJump.to) {
      linkReturn = pendingLinkJump.from; undoPageJump.hidden = false;
      linkTimer = setTimeout(clearLinkReturn, 3000)
    }
    pendingLinkJump = null
  }
};
