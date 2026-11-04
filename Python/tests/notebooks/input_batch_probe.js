(()=>{
  const original = {active, last, points, mode, pan, frameBatchedInk, nativePen: state.native_pen,
    rectangle: canvas.getBoundingClientRect, ownRectangle: Object.hasOwn(canvas, 'getBoundingClientRect'),
    schedule: schedulePreview};
  let reads = 0, previews = 0;
  let rectangle = {left: 10, top: 20, width: 200, height: 100};
  function check(value, message) { if (!value) throw new Error(message) }
  function event(x, y, pressure, extra = {}) {
    return {pointerId: 42, pointerType: 'pen', clientX: x, clientY: y, pressure,
      preventDefault() {}, ...extra}
  }
  function expectPoint(point, expected) {
    check(point.length === expected.length && point.every((value, i) => Math.abs(value - expected[i]) < 1e-8),
      'Input coordinates or pressure changed: ' + JSON.stringify(point));
  }
  try {
    active = 42; last = null; points = []; mode = 'ink'; pan = null;
    frameBatchedInk = true; state.native_pen = false;
    canvas.getBoundingClientRect = () => { reads++; return rectangle };
    schedulePreview = () => { previews++ };
    canvas.onpointermove(event(110, 70, .8, {getCoalescedEvents: () => [event(30, 30, .2), event(110, 70, .8)]}));
    check(reads === 1 && previews === 1 && points.length === 2, 'Coalesced input did not use one bounds read or lost deduplication');
    expectPoint(points[0], [state.width * .1, state.height * .1, .2]);
    expectPoint(points[1], [state.width * .5, state.height * .5, .8]);

    // A later delivery must use the new layout, even within one gesture.
    rectangle = {left: 20, top: 40, width: 100, height: 200};
    canvas.onpointermove(event(70, 140, 1, {pointerType: 'mouse'}));
    check(reads === 2 && previews === 2 && points.length === 3, 'The next batch reused stale geometry');
    expectPoint(points[2], [state.width * .5, state.height * .5, .5]);

    canvas.onpointermove(event(9999, -9999, 0));
    check(reads === 3 && points.length === 4, 'Fallback event was not sampled');
    expectPoint(points[3], [state.width, 0, 0]);

    canvas.onpointermove(event(50, 50, .5, {pointerId: 43}));
    state.native_pen = true;
    canvas.onpointermove(event(50, 50, .5, {isTrusted: true}));
    check(reads === 3 && points.length === 4, 'Ignored input measured layout or changed ink');
    canvas.onpointermove(event(50, 50, .5, {isTrusted: true, nativePen: true}));
    check(reads === 4 && points.length === 5, 'Native pen batch was not accepted');
    expectPoint(points[4], [state.width * .3, state.height * .05, .5]);
    return {passed: true, cases: 6, accepted_batches: 4, bounds_reads: reads};
  } finally {
    active = original.active; last = original.last; points = original.points;
    mode = original.mode; pan = original.pan; frameBatchedInk = original.frameBatchedInk;
    state.native_pen = original.nativePen; schedulePreview = original.schedule;
    if (original.ownRectangle) canvas.getBoundingClientRect = original.rectangle;
    else delete canvas.getBoundingClientRect;
  }
})()
