// OS palm cancellation remains authoritative. This guard also keeps a resting
// hand from starting a canvas gesture while a detected pen is nearby/in use.
const penReleaseGrace = 350;
const penHoverSources = new Set();
let penContactActive = false, penBlockedUntil = 0;
function penTouchBlocked() {
  return penContactActive || penHoverSources.size > 0 || performance.now() < penBlockedUntil
}
function rejectPendingTouch() {
  // Cancel an unfinished finger stroke/pan/pinch, never the pen's own stroke.
  if (typeof cancelTouchZoom === 'function') cancelTouchZoom();
  if (pan) pan = null
}
function notePenContact(down) {
  if (down) rejectPendingTouch();
  penContactActive = down;
  if (!down) penBlockedUntil = performance.now() + penReleaseGrace
}
function notePenHover(source, nearby) {
  if (nearby) {
    penHoverSources.add(source);
    rejectPendingTouch()
  } else if (penHoverSources.delete(source)) {
    penBlockedUntil = performance.now() + penReleaseGrace
  }
}
function resetPenRejection() {
  if (penContactActive && active !== null) finish({pointerId: active, pointerType: 'pen', nativePen: true}, true);
  penContactActive = false;
  penHoverSources.clear();
  penBlockedUntil = 0;
  rejectPendingTouch()
}
function rejectPalmEvent(event) {
  if (event.pointerType !== 'touch' || !penTouchBlocked()) return false;
  event.preventDefault();
  event.stopImmediatePropagation();
  return true
}
// Register before pinch/pan listeners. Rejected contacts never enter their maps
// and cannot resume halfway through a gesture after the grace period expires.
for (const name of ['pointerdown', 'pointermove', 'pointerup', 'pointercancel'])
  $('viewport').addEventListener(name, rejectPalmEvent, {capture: true, passive: false});
canvas.addEventListener('pointerenter', event => {
  if (event.pointerType === 'pen') notePenHover('browser', true)
});
canvas.addEventListener('pointerleave', event => {
  if (event.pointerType === 'pen') notePenHover('browser', false)
});
canvas.addEventListener('pointermove', event => {
  if (event.pointerType === 'pen' && !event.buttons) notePenHover('browser', true)
});
// Native hover adapters use WebView-relative coordinates. A pen above toolbar
// chrome does not disable document finger gestures.
window.logisticsPenProximity = (nearby, x = 0, y = 0, width = innerWidth, height = innerHeight) => {
  const overPaper = nearby && width > 0 && height > 0 &&
    document.elementFromPoint(x * innerWidth / width, y * innerHeight / height) === canvas;
  notePenHover('native', !!overPaper)
};
window.addEventListener('blur', resetPenRejection);
document.addEventListener('visibilitychange', () => {if (document.hidden) resetPenRejection()});
