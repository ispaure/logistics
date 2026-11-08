// Link gestures own no ink commands. Only completed taps can navigate.
let linkGesture = null, pendingPageFeedback = null, linkReturn = null, pageFeedbackTimer = null;
const pageFeedback = document.createElement('div');
pageFeedback.id = 'pageNavigationFeedback';
pageFeedback.hidden = true;
const pageFeedbackLabel = document.createElement('span');
pageFeedbackLabel.setAttribute('role', 'status');
const undoPageJump = document.createElement('button');
undoPageJump.id = 'undoPageJump';
undoPageJump.type = 'button';
undoPageJump.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 5-5 5 5 5M3 10h10a7 7 0 0 1 7 7v2"/></svg>Go back';
undoPageJump.hidden = true;
pageFeedback.append(pageFeedbackLabel, undoPageJump);
document.body.append(pageFeedback);
const linkFeedback = document.createElement('canvas');
linkFeedback.id = 'linkFeedback';
linkFeedback.hidden = true;
linkFeedback.setAttribute('aria-hidden', 'true');
$('inkLayers').append(linkFeedback);

function showLinkFeedback(link) {
  const bounds = backgroundContentBounds();
  if (!bounds || !canvas.width || !canvas.height) return;
  const [left, top, right, bottom] = link.rect;
  const x = (bounds.x + left * bounds.width) / state.width;
  const y = (bounds.y + top * bounds.height) / state.height;
  const width = (right - left) * bounds.width / state.width;
  const height = (bottom - top) * bounds.height / state.height;
  Object.assign(linkFeedback.style, {
    left: 100 * x + '%', top: 100 * y + '%', width: 100 * width + '%', height: 100 * height + '%'
  });
  linkFeedback.width = Math.ceil(width * canvas.width);
  linkFeedback.height = Math.ceil(height * canvas.height);
  const preview = linkFeedback.getContext('2d');
  if (!preview) return;
  preview.drawImage(canvas, x * canvas.width, y * canvas.height,
    width * canvas.width, height * canvas.height, 0, 0, linkFeedback.width, linkFeedback.height);
  linkFeedback.hidden = false
}
function clearPageFeedback() {
  clearTimeout(pageFeedbackTimer);
  pageFeedbackTimer = null;
  linkReturn = null;
  pageFeedback.hidden = undoPageJump.hidden = true
}
function showPageFeedback(from) {
  const mobile = mobileViewport();
  clearPageFeedback();
  if (!mobile && from === null) return;
  linkReturn = from;
  pageFeedback.hidden = false;
  pageFeedbackLabel.textContent = 'Page ' + (state.index + 1) + ' of ' + state.count;
  if (from !== null) {
    undoPageJump.setAttribute('aria-label', 'Go back to page ' + (from + 1));
    undoPageJump.hidden = false
  }
  if (from === null || !mobile) pageFeedbackTimer = setTimeout(clearPageFeedback, 3000)
}
function navigateWithPageFeedback(index, from = null) {
  const action = {op: 'page', index};
  pendingPageFeedback = {action, from};
  send(action)
}
undoPageJump.onclick = () => {
  if (busy || active !== null || linkReturn === null) return;
  navigateWithPageFeedback(linkReturn)
};
function notebookLinkAt(e) {
  if (!state.links?.length) return;
  const bounds = backgroundContentBounds();
  if (!bounds) return;
  const [x, y] = coord(e);
  const px = (x - bounds.x) / bounds.width, py = (y - bounds.y) / bounds.height;
  return state.links.find(link => {
    const [l,t,r,b] = link.rect; return px >= l && px <= r && py >= t && py <= b
  })
}
const linkDown = canvas.onpointerdown, linkMove = canvas.onpointermove,
  linkUp = canvas.onpointerup, linkCancel = canvas.onpointercancel;
document.addEventListener('pointerdown', e => {
  if (linkGesture && e.pointerId !== linkGesture.id) linkGesture.cancelled = true
}, true);
canvas.onpointerdown = e => {
  if (typeof mode !== 'undefined' && (mode === 'select' || mode === 'capture')) return linkDown(e);
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
      if (index >= 0 && index < state.count) navigateWithPageFeedback(index)
    }
    return
  }
  e.preventDefault();
  if (gesture.link.index !== state.index) {
    showLinkFeedback(gesture.link);
    navigateWithPageFeedback(gesture.link.index, state.index)
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
  const completed = queue[0], previous = state.page_id ?? state.index;
  linkUpdate(next, error);
  if (state !== next) return;  // The command can wait for an active stroke.
  if ((next.page_id ?? next.index) !== previous) clearPageFeedback();
  if (pendingPageFeedback && completed === pendingPageFeedback.action) {
    const {action, from} = pendingPageFeedback;
    pendingPageFeedback = null;
    linkFeedback.hidden = true;
    linkFeedback.width = linkFeedback.height = 0;
    if (!error && next.index === action.index) showPageFeedback(from)
  }
};
