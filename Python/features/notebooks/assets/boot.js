// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

$('grayscale').onchange = () => draw();
let resizeFrame = null, viewportResizePending = false;
function scheduleViewportResize() {
  if (resizeFrame !== null) return;
  resizeFrame = requestAnimationFrame(() => {
    resizeFrame = null;
    if (active === null) resize();
    else viewportResizePending = true
  })
}
new ResizeObserver(scheduleViewportResize).observe($('viewport'));
render();
