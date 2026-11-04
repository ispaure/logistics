// Run with Node, or require this driver from the host V8 tool. This checks the
// production palm guard with an explicit clock, not UIKit/Android hardware.
const vm = require('node:vm');
function checkPalmRejection(source) {
  const listeners = {viewport: {}, canvas: {}, window: {}, document: {}};
  const target = key => ({addEventListener(name, callback) {listeners[key][name] = callback}});
  const canvas = target('canvas'), viewport = target('viewport');
  let now = 1000, cancelledTouches = 0, cancelledPens = 0;
  const context = {Set, innerWidth: 400, innerHeight: 700, active: null, pan: null,
    performance: {now: () => now}, canvas, $: () => viewport,
    window: target('window'), document: {...target('document'), hidden: false,
      elementFromPoint: (x, y) => x > 0 && x < 400 && y > 0 && y < 700 ? canvas : null},
    cancelTouchZoom() {cancelledTouches++; if (context.active === 'finger') context.active = null},
    finish(event, cancelled) {if (cancelled && event.nativePen) cancelledPens++; context.active = null}
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  const run = command => vm.runInContext(command, context);
  const check = (value, message) => {if (!value) throw Error(message)};
  const touch = () => ({pointerType: 'touch', prevented: false, stopped: false,
    preventDefault() {this.prevented = true}, stopImmediatePropagation() {this.stopped = true}});
  check(!run('penTouchBlocked()'), 'Finger input must work before any pen detection');
  let event = touch(); listeners.viewport.pointerdown(event);
  check(!event.prevented && !event.stopped, 'Ordinary finger contact was swallowed');

  context.active = 'finger'; context.pan = {id: 'finger'};
  context.window.logisticsPenProximity(true, 100, 100, 400, 700);
  check(run('penTouchBlocked()') && context.active === null && context.pan === null && cancelledTouches > 0,
    'Pen proximity did not cancel the pending finger gesture');
  for (const name of ['pointerdown', 'pointermove', 'pointerup', 'pointercancel']) {
    event = touch(); listeners.viewport[name](event);
    check(event.prevented && event.stopped, 'Palm event escaped the capture guard: ' + name)
  }
  now += 10000;
  check(run('penTouchBlocked()'), 'Stationary detected hover expired without exit');
  context.window.logisticsPenProximity(true, -100, -100, 400, 700);
  check(run('penTouchBlocked()'), 'Hover exit skipped the grace period');
  now += 351;
  check(!run('penTouchBlocked()'), 'Pen over toolbar left finger input blocked');

  run('notePenContact(true)');
  now += 10000;
  check(run('penTouchBlocked()'), 'A long pen contact lost palm rejection');
  run('notePenContact(false)');
  now += 349;
  check(run('penTouchBlocked()'), 'Pen-up grace period ended too early');
  now += 2;
  check(!run('penTouchBlocked()'), 'Finger input did not recover after grace period');

  listeners.canvas.pointerenter({pointerType: 'pen'});
  check(run('penTouchBlocked()'), 'Browser Pencil/pen hover was not observed');
  listeners.canvas.pointerleave({pointerType: 'pen'});
  now += 351;
  check(!run('penTouchBlocked()'), 'Browser hover exit remained latched');
  listeners.canvas.pointerenter({pointerType: 'mouse'});
  check(!run('penTouchBlocked()'), 'A trackpad/mouse incorrectly triggered palm rejection');

  context.active = 'pen'; run('notePenContact(true)');
  listeners.window.blur();
  check(cancelledPens === 1 && !run('penTouchBlocked()'), 'Blur did not cancel the pen and reset proximity');
  context.window.logisticsPenProximity(true, 100, 100, 400, 700);
  context.document.hidden = true; listeners.document.visibilitychange();
  check(!run('penTouchBlocked()'), 'Hidden document retained stale pen proximity');
  return {passed: true, cases: 6, scope: 'shared palm guard logic; no hardware or full DOM proof'}
}
module.exports = checkPalmRejection;
if (require.main === module) {
  const fs = require('node:fs'), path = require('node:path');
  console.log(JSON.stringify(checkPalmRejection(fs.readFileSync(path.join(__dirname,
    '../../features/notebooks/assets/palm.js'), 'utf8'))));
}
