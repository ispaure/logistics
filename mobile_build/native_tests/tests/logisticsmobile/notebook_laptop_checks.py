"""Shared real-browser checks for upper settings and lower notebook ink."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

LAPTOP_CHECKS = r"""JSON.stringify((() => {
  const check = (ok, message) => { if (!ok) throw Error(message); };
  const tools = $('laptopTools').getBoundingClientRect(), viewport = $('viewport').getBoundingClientRect();
  check(document.body.classList.contains('notebook-laptop'), 'Laptop layout missing');
  check(tools.bottom <= innerHeight * .48 + 1, 'Tools cross the hinge');
  check(viewport.top >= innerHeight * .52 - 1, 'Canvas crosses the hinge');
  check(!$('viewport').inert, 'Canvas blocked by tools');
  for (const id of ['tool','color','width','layer','zoom','finger','grayscale'])
    check($('laptopTools').contains($(id)), id + ' is not in upper settings');
  const brushes = [...document.querySelectorAll('.brush-card')];
  check(brushes.length === Object.keys(state.tools).length && brushes.every(b => b.getClientRects().length), 'Brushes collapsed');
  brushes.find(b => b.dataset.tool === '17').click();
  const color = document.querySelector('.swatch:last-child'); color.click();
  const width = document.querySelector('.widths button:last-child'); width.click();
  check(color.getAttribute('aria-pressed') === 'true' && width.getAttribute('aria-pressed') === 'true', 'Settings not selected');
  $('zoom').value='page'; $('zoom').onchange();
  const r = canvas.getBoundingClientRect();
  check(r.top >= viewport.top - 1 && r.bottom <= viewport.bottom + 1, 'Fitted paper leaves lower screen');
  const originalSend=send, actions=[];
  send=action=>actions.push(action);
  try {
    const event = (x,y) => ({pointerId:991,pointerType:'pen',nativePen:true,pressure:.6,
      clientX:r.left+r.width*x,clientY:r.top+r.height*y,preventDefault(){}});
    canvas.onpointerdown(event(.25,.25)); finish(event(.5,.5));
    check(actions.length === 1 && actions[0].op === 'stroke', 'Lower screen did not draw');
    const first=actions[0].points[0];
    check(Math.abs(first[0]-state.width*.25)<1 && Math.abs(first[1]-state.height*.25)<1, 'Stroke coordinates shifted');
    check(!$('laptopTools').hidden && !$('viewport').inert, 'Drawing dismissed settings');
    return {tools:tools.toJSON(),viewport:viewport.toJSON(),brushes:brushes.length,stroke:actions[0].op};
  } finally {send=originalSend;}
})())"""
