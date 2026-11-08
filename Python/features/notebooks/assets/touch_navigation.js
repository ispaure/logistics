// Single-finger navigation owns no ink.
let pageTouch = null, offeredPage = null, addingSwipePage = false;
const swipeAddPage = document.createElement('button');
swipeAddPage.id = 'swipeAddPage';
swipeAddPage.type = 'button';
swipeAddPage.hidden = true;
swipeAddPage.title = 'Add a page after the last page';
swipeAddPage.setAttribute('aria-label', 'Add page after the last page');
swipeAddPage.innerHTML = '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M14 3H4v18h16V9l-6-6Zm0 0v6h6M12 12v6m-3-3h6"/></svg><span>Page</span>';
swipeAddPage.style.cssText = 'position:fixed;z-index:3;min-width:52px;min-height:52px;padding:8px;display:flex;flex-direction:column;align-items:center;gap:3px';
// An explicit hidden rule wins over the inline flex layout on every backend.
swipeAddPage.style.display = 'none';
document.body.append(swipeAddPage);
function hideSwipePage() {
  offeredPage = null;
  swipeAddPage.hidden = true;
  swipeAddPage.style.display = 'none'
}
function showSwipePage() {
  if (state.read_only || state.password_required || state.warning) return;
  const box = $('viewport').getBoundingClientRect();
  offeredPage = state.page_id ?? state.index;
  swipeAddPage.style.right = 'max(calc(var(--notebook-rail-right, 0px) + 12px), ' + (innerWidth - box.right + 12) + 'px)';
  swipeAddPage.style.top = Math.max(box.top+8, box.top+(box.height-76)/2)+'px';
  swipeAddPage.hidden = false;
  swipeAddPage.style.display = 'flex'
}
swipeAddPage.onclick = () => {
  if (busy || active !== null || touchContacts.size || state.read_only || state.password_required ||
      state.warning || state.index !== state.count-1 || offeredPage !== (state.page_id ?? state.index)) return;
  addingSwipePage = true;
  swipeAddPage.disabled = true;
  send({op: 'add-page'})
};
function finishPageSwipe(gesture, event) {
  const dx = event.clientX-gesture.x, dy = event.clientY-gesture.y;
  if (busy || gesture.index !== state.index || gesture.vertical || performance.now()-gesture.time >= 900 ||
      Math.abs(dx) < 48 || Math.abs(dx) <= Math.abs(dy)*1.5) return false;
  const index = state.index+(dx < 0 ? 1 : -1);
  if (index >= 0 && index < state.count) {
    hideSwipePage();
    navigateWithPageFeedback(index)
  } else if (dx < 0 && index === state.count) showSwipePage();
  return true
}
function cancelPageTouch(removeContact = false) {
  if (!pageTouch) return;
  const gesture = pageTouch;
  pageTouch = null;
  canvas.onpointercancel({pointerId: gesture.id, pointerType: 'touch',
    clientX: gesture.x, clientY: gesture.y, preventDefault() {}});
  if (pan?.id === gesture.id) pan = null;
  if (removeContact) touchContacts.delete(gesture.id)
}
function pageTouchTarget(event) {
  const viewport = $('viewport');
  return (event.target === viewport || viewport.contains(event.target)) &&
    !event.target.closest('button,input,select,textarea,a,dialog')
}
document.addEventListener('pointerdown', event => {
  if (pageTouch && event.pointerId !== pageTouch.id) cancelPageTouch();
  if (event.pointerType !== 'touch' || !pageTouchTarget(event) || penTouchBlocked() ||
      touchZoomBlocked || touchContacts.size || active !== null) return;
  // Finger drawing and explicit lasso/capture tools keep their editing gesture.
  if (event.target === canvas && (mode === 'select' || mode === 'capture' ||
      ($('finger').checked && !notebookLinkAt(event)))) return;
  pageTouch = {id: event.pointerId, x: event.clientX, y: event.clientY,
    index: state.index, time: performance.now(), moved: false, vertical: false}
}, true);
document.addEventListener('pointermove', event => {
  if (pageTouch?.id !== event.pointerId) return;
  const gesture = pageTouch;
  for (const sample of [...(event.getCoalescedEvents?.() || []), event]) {
    const dx = sample.clientX-gesture.x, dy = sample.clientY-gesture.y;
    if (Math.hypot(dx, dy) > 8) gesture.moved = true;
    if (Math.abs(dy) > 12 && Math.abs(dy) > Math.abs(dx)*1.5) gesture.vertical = true
  }
  // Keep the first contact's actual position for a subsequent two-finger pan.
  if (touchContacts.has(event.pointerId)) touchContacts.set(event.pointerId, {x: event.clientX, y: event.clientY});
  if (penTouchBlocked() || pan?.id !== event.pointerId) cancelPageTouch();
  event.preventDefault();
  event.stopImmediatePropagation()
}, {capture: true, passive: false});
document.addEventListener('pointerup', event => {
  if (pageTouch?.id !== event.pointerId) return;
  const gesture = pageTouch;
  const owned = pan?.id === event.pointerId && !pan.cancelled && !penTouchBlocked();
  if (owned && finishPageSwipe(gesture, event)) {
    cancelPageTouch(true);
  } else if (!owned || gesture.moved || gesture.index !== state.index) {
    cancelPageTouch(true);
  } else {
    pageTouch = null;
    return  // A stationary finger tap can still follow an internal PDF link.
  }
  event.preventDefault();
  event.stopImmediatePropagation()
}, {capture: true, passive: false});
for (const name of ['pointercancel', 'lostpointercapture']) document.addEventListener(name, event => {
  if (pageTouch?.id === event.pointerId) cancelPageTouch(true)
}, true);
window.addEventListener('blur', () => cancelPageTouch());
window.addEventListener('resize', () => {if (!swipeAddPage.hidden) showSwipePage()});
const pageTouchUpdate = window.notebookUpdate;
window.notebookUpdate = (next, error) => {
  const completed = queue[0], previous = state.page_id ?? state.index;
  pageTouchUpdate(next, error);
  if (previous !== (next.page_id ?? next.index) || next.index !== next.count-1 || next.read_only || next.password_required)
    hideSwipePage();
  if (addingSwipePage && completed?.op === 'add-page') {
    addingSwipePage = false;
    if (error) showSwipePage();
    else hideSwipePage()
  }
  swipeAddPage.disabled = busy || active !== null
};
