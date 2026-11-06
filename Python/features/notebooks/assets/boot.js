$('grayscale').onchange = () => draw();
let resizeFrame = null, viewportResizePending = false;
new ResizeObserver(() => {
  if (resizeFrame !== null) return;
  resizeFrame = requestAnimationFrame(() => {
    resizeFrame = null;
    if (active === null) resize();
    else viewportResizePending = true
  })
}).observe($('viewport'));
render();
