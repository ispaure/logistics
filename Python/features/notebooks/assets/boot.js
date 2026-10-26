$('grayscale').onchange = draw;
$('zoom').onchange = resize;
let resizeFrame = null;
new ResizeObserver(() => {
  if (resizeFrame !== null) return;
  resizeFrame = requestAnimationFrame(() => {
    resizeFrame = null;
    if (active === null) resize()
  })
}).observe($('viewport'));
render();
