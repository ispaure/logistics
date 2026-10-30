const palette = state.palette,
  brushes = state.brushes;
const aliases = {
  0: 12,
  1: 14,
  2: 15,
  3: 16,
  4: 17,
  5: 18,
  7: 13
};
const draft = $('draft'),
  draftCtx = draft.getContext('2d');
const mask = document.createElement('canvas'),
  maskCtx = mask.getContext('2d');
let draftCount = 0;
let inkSettings = null;
let frameBatchedInk = false;
let draftBounds = null,
  previewFrame = null,
  previewCount = 0;

function brushFor(tool) {
  return brushes[aliases[tool] ?? tool] || brushes[17]
}

function brushOptions() {
  let brush = brushFor(Number($('tool').value));
  options('color', brush.colors.map(id => Object.entries(state.colors).find(([name, value]) => value === id)));
  if (!$('width').options.length) {
    options('width', Object.entries(state.widths));
    $('width').value = '2'
  }
}

function chosenInk() {
  return {
    tool: Number($('tool').value),
    color: Number($('color').value),
    width: Number($('width').value),
    layer: $('layer').value
  }
}

function nativeColor(tool, color) {
  if (tool === 18) return {
    color: 9,
    color_rgba: state.highlights[color]
  };
  if (tool === 23) return {
    color: 9,
    color_rgba: state.shaders[color]
  };
  return {
    color,
    color_rgba: null
  };
}

function strokePoint(samples, i, tool, width) {
  let brush = brushFor(tool),
    base = brush.widths[width - 1],
    [x, y, p] = samples[i];
  let w = base * (1 - brush.pressure + brush.pressure * Math.pow(p, brush.exponent));
  if (brush.directional) {
    let before = samples[i ? i - 1 : Math.min(1, samples.length - 1)],
      angle = Math.atan2(y - before[1], x - before[0]);
    let delta = angle - brush.nib_angle;
    w *= Math.hypot(Math.sin(delta), brush.nib_ratio * Math.cos(delta))
  }
  return [x, y, p, Math.max(.25, Math.round(w * 4) / 4)];
}

function strokePoints(samples, tool, width) {
  return samples.map((p, i) => strokePoint(samples, i, tool, width))
}

function inkColor(s) {
  let rgba = s.color_rgba,
    hex = palette[s.color] || '#000000',
    rgb = rgba ? rgba.slice(0, 3) : [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
  if ($('grayscale').checked) {
    let gray = Math.round(.2126 * rgb[0] + .7152 * rgb[1] + .0722 * rgb[2]);
    rgb = [gray, gray, gray]
  }
  return {
    rgb,
    alpha: rgba ? rgba[3] / 255 : 1
  };
}

function colorCss(rgb) {
  return 'rgb(' + rgb.join(',') + ')'
}

function swatchColor(tool, color) {
  let {
    rgb,
    alpha
  } = inkColor(nativeColor(tool, color));
  return rgb.map(v => Math.round(v * alpha + 255 * (1 - alpha)))
}
const grainCache = new Map();

function grain(target, rgb, mechanical) {
  let key = rgb.join(',') + mechanical;
  if (grainCache.has(key)) return grainCache.get(key);
  let tile = document.createElement('canvas');
  tile.width = tile.height = 8;
  let g = tile.getContext('2d');
  g.fillStyle = colorCss(rgb);
  g.globalAlpha = mechanical ? .75 : .6;
  g.fillRect(0, 0, 8, 8);
  for (let y = 0; y < 8; y++)
    for (let x = 0; x < 8; x++) {
      g.globalAlpha = ((x * 13 + y * 7) % 11) / 14;
      g.fillRect(x, y, 1, 1)
    }
  let pattern = target.createPattern(tile, 'repeat');
  grainCache.set(key, pattern);
  return pattern;
}

// Stored point arrays are immutable; full updates replace them. Weak ownership
// lets retired page/undo geometry go with its model instead of retaining a
// second document. Reuse the exact path rather than rebuilding every arc on
// each eraser acknowledgement, scroll/layout redraw or selection update.
const ribbonCache = new WeakMap();
function ribbon(target, p) {
  if (ribbonCache.has(p)) {
    target.fill(ribbonCache.get(p));
    return
  }
  const path = new Path2D();
  for (let i = 0; i < p.length; i++) {
    let b = p[i],
      r = b[3] / 2;
    path.moveTo(b[0] + r, b[1]);
    path.arc(b[0], b[1], r, 0, Math.PI * 2);
    if (!i) continue;
    let a = p[i - 1],
      dx = b[0] - a[0],
      dy = b[1] - a[1],
      length = Math.hypot(dx, dy);
    if (!length) continue;
    let nx = -dy / length,
      ny = dx / length,
      ar = a[3] / 2;
    // Consistent winding makes the overlapping segment outlines one filled mask.
    path.moveTo(a[0] + nx * ar, a[1] + ny * ar);
    path.lineTo(a[0] - nx * ar, a[1] - ny * ar);
    path.lineTo(b[0] - nx * r, b[1] - ny * r);
    path.lineTo(b[0] + nx * r, b[1] + ny * r);
    path.closePath();
  }
  ribbonCache.set(p, path);
  target.fill(path);
}

function geometry(target, p, family, beforePoint = null) {
  if (family === 'calligraphy') {
    // A fixed broad nib. Recover its span from each stored perpendicular width;
    // imported pressure/width is never applied a second time.
    let angle = brushes[21].nib_angle, ratio = brushes[21].nib_ratio,
      ux = Math.cos(angle), uy = Math.sin(angle), vx = -uy, vy = ux;
    let nib = p.map((point, i) => {
      let before = i ? p[i - 1] : beforePoint || p[Math.min(1, p.length - 1)],
        direction = Math.atan2(point[1] - before[1], point[0] - before[0]),
        radius = point[3] / (2 * Math.hypot(Math.sin(direction - angle), ratio * Math.cos(direction - angle)));
      return {point, radius}
    });
    const edge = (item, nx, ny) => {
      let du = nx * ux + ny * uy, dv = nx * vx + ny * vy,
        divisor = Math.hypot(du, ratio * dv) || 1;
      return [item.point[0] + item.radius * (ux * du + vx * ratio * ratio * dv) / divisor,
        item.point[1] + item.radius * (uy * du + vy * ratio * ratio * dv) / divisor]
    };
    target.beginPath();
    for (let i = 0; i < nib.length; i++) {
      let b = nib[i];
      target.moveTo(b.point[0] + ux * b.radius, b.point[1] + uy * b.radius);
      target.ellipse(b.point[0], b.point[1], b.radius, b.radius * ratio, angle, 0, Math.PI * 2);
      if (!i) continue;
      let a = nib[i - 1], dx = b.point[0] - a.point[0], dy = b.point[1] - a.point[1],
        length = Math.hypot(dx, dy);
      if (!length) continue;
      let nx = -dy / length, ny = dx / length,
        corners = [edge(a, nx, ny), edge(a, -nx, -ny), edge(b, -nx, -ny), edge(b, nx, ny)];
      target.moveTo(...corners[0]);
      for (let point of corners.slice(1)) target.lineTo(...point);
      target.closePath()
    }
    target.fill()
  } else if (['fineliner', 'mechanical', 'highlighter'].includes(family) && p.length > 1 && p[0][3] > 0 && p.every(v => v[3] === p[0][3])) {
    target.lineWidth = p[0][3];
    target.beginPath();
    target.moveTo(p[0][0], p[0][1]);
    for (let i = 1; i < p.length; i++) target.lineTo(p[i][0], p[i][1]);
    target.stroke();
  } else ribbon(target, p);
}

const filteredInkBounds = new WeakMap();
function clipPaintbrush(target, points) {
  // Bound filtered paint work to actual ink, including when operations queue
  // on a software/emulated GPU. Stored geometry is immutable: weak ownership
  // preserves the path cache's cheap redraws without retaining retired pages.
  let bounds = filteredInkBounds.get(points);
  if (!bounds) {
    bounds = points.reduce((b, p) => {
      const radius = p[3] / 2;
      return [Math.min(b[0], p[0] - radius), Math.min(b[1], p[1] - radius),
        Math.max(b[2], p[0] + radius), Math.max(b[3], p[1] + radius)]
    }, [Infinity, Infinity, -Infinity, -Infinity]);
    filteredInkBounds.set(points, bounds)
  }
  const matrix = target.getTransform(),
    scale = Math.max(1e-6, Math.min(Math.hypot(matrix.a, matrix.b), Math.hypot(matrix.c, matrix.d))),
    fringe = 4 + 2 / scale;
  target.beginPath();
  target.rect(bounds[0] - fringe, bounds[1] - fringe,
    bounds[2] - bounds[0] + 2 * fringe, bounds[3] - bounds[1] + 2 * fringe);
  target.clip();
}

function line(s, target = ctx) {
  let p = s.points;
  if (!p.length) return;
  let brush = brushFor(s.tool),
    family = brush.family,
    {
      rgb,
      alpha
    } = inkColor(s);
  target.save();
  target.fillStyle = target.strokeStyle = colorCss(rgb);
  target.lineCap = 'round';
  target.lineJoin = 'round';
  target.globalAlpha = alpha;
  if (brush.texture) target.fillStyle = target.strokeStyle = grain(target, rgb, family === 'mechanical');
  if (family === 'highlighter') {
    target.globalCompositeOperation = 'darken';
    target.lineCap = 'butt'
  }
  if (family === 'shader') {
    target.globalCompositeOperation = 'multiply';
    if (!s.color_rgba) target.globalAlpha = .25
  }
  if (family === 'paintbrush') {
    target.filter = 'blur(.4px)';
    target.globalAlpha *= .85
  }
  if (family === 'marker') target.globalAlpha *= .9;
  if (family === 'paintbrush') {
    target.save();
    clipPaintbrush(target, p);
    geometry(target, p, family);
    target.restore()
  } else geometry(target, p, family);
  if (selected.has(s.id)) {
    target.globalAlpha = 1;
    target.globalCompositeOperation = 'source-over';
    target.filter = 'none';
    target.strokeStyle = '#2877cb';
    target.lineWidth = 2;
    let bounds = p.reduce((b, p) => [Math.min(b[0], p[0] - p[3] / 2), Math.min(b[1], p[1] - p[3] / 2), Math.max(b[2], p[0] + p[3] / 2), Math.max(b[3], p[1] + p[3] / 2)], [Infinity, Infinity, -Infinity, -Infinity]);
    target.strokeRect(bounds[0] - 5, bounds[1] - 5, bounds[2] - bounds[0] + 10, bounds[3] - bounds[1] + 10)
  }
  target.restore();
}

function clearDraft() {
  draftCtx.clearRect(0, 0, state.width, state.height);
  maskCtx.clearRect(0, 0, state.width, state.height);
  draftCount = 0;
  draftBounds = null
}

function sizeDraft() {
  draft.width = mask.width = canvas.width;
  draft.height = mask.height = canvas.height;
  draft.style.width = canvas.style.width;
  draft.style.height = canvas.style.height;
  for (let target of [draftCtx, maskCtx]) target.setTransform(canvas.width / state.width, 0, 0, canvas.height / state.height, 0, 0);
  draftCount = 0;
  draftBounds = null;
}

function commitDraft(tool) {
  if (draftBounds) {
    let [left, top, right, bottom] = draftBounds,
      family = brushFor(tool).family;
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalCompositeOperation = family === 'highlighter' ? 'darken' : family === 'shader' ? 'multiply' : 'source-over';
    // Keep pen-up work bounded to painted pixels, instead of replaying the
    // complete stroke or compositing an entire transparent page.
    ctx.drawImage(draft, left, top, right - left, bottom - top, left, top, right - left, bottom - top);
    ctx.restore();
  }
  clearDraft();
}

function cancelPreview() {
  if (previewFrame !== null) cancelAnimationFrame(previewFrame);
  previewFrame = null;
  previewCount = 0;
}

function flushPreview() {
  if (previewFrame !== null) cancelAnimationFrame(previewFrame);
  previewFrame = null;
  if (mode === 'ink' && points.length > previewCount) {
    preview(points.slice(Math.max(0, previewCount - 1)));
    previewCount = points.length
  }
}

function schedulePreview() {
  if (previewFrame === null) previewFrame = requestAnimationFrame(flushPreview);
}

function preview(samples) {
  let settings = inkSettings || chosenInk(),
    {
      tool,
      color,
      width
    } = settings,
    brush = brushFor(tool);
  if (['fineliner', 'ballpoint'].includes(brush.family)) {
    line({
      tool,
      ...nativeColor(tool, color),
      points: strokePoints(samples, tool, width)
    }, ctx);
    return;
  }
  // Accumulate opaque geometry in a mask. Recolor only the new segment's bounds,
  // applying texture and alpha once. Work per move is independent of stroke length.
  if (draftCount > points.length || (draftCount === 1 && points.length > 1)) clearDraft();
  let pending = [], first = Math.max(0, draftCount - 1), beforePoint = first ? points[first - 1] : null;
  for (let i = first; i < points.length; i++) pending.push(strokePoint(points, i, tool, width));
  if (!pending.length) return;
  let family = brush.family,
    {
      rgb,
      alpha
    } = inkColor(nativeColor(tool, color));
  draft.style.mixBlendMode = family === 'highlighter' ? 'darken' : family === 'shader' ? 'multiply' : 'normal';
  maskCtx.save();
  maskCtx.fillStyle = maskCtx.strokeStyle = 'white';
  maskCtx.lineCap = family === 'highlighter' ? 'butt' : 'round';
  maskCtx.lineJoin = 'round';
  if (family === 'paintbrush') {
    maskCtx.filter = 'blur(.4px)';
    clipPaintbrush(maskCtx, pending)
  }
  geometry(maskCtx, pending, family, beforePoint);
  if (family === 'highlighter' && draftCount >= 2) {
    let p = pending[0];
    maskCtx.beginPath();
    maskCtx.arc(p[0], p[1], p[3] / 2, 0, Math.PI * 2);
    maskCtx.fill()
  }
  maskCtx.restore();
  draftCount = points.length;
  let bounds = pending.reduce((b, p) => {
    let radius = family === 'calligraphy' ? p[3] / (2 * brush.nib_ratio) : p[3] / 2;
    return [Math.min(b[0], p[0] - radius - 4), Math.min(b[1], p[1] - radius - 4), Math.max(b[2], p[0] + radius + 4), Math.max(b[3], p[1] + radius + 4)]
  }, [Infinity, Infinity, -Infinity, -Infinity]);
  let sx = canvas.width / state.width,
    sy = canvas.height / state.height;
  let left = Math.max(0, Math.floor(bounds[0] * sx)),
    top = Math.max(0, Math.floor(bounds[1] * sy)),
    right = Math.min(canvas.width, Math.ceil(bounds[2] * sx)),
    bottom = Math.min(canvas.height, Math.ceil(bounds[3] * sy));
  if (right <= left || bottom <= top) return;
  draftBounds = draftBounds ? [Math.min(left, draftBounds[0]), Math.min(top, draftBounds[1]), Math.max(right, draftBounds[2]), Math.max(bottom, draftBounds[3])] : [left, top, right, bottom];
  draftCtx.save();
  draftCtx.setTransform(1, 0, 0, 1, 0, 0);
  draftCtx.beginPath();
  draftCtx.rect(left, top, right - left, bottom - top);
  draftCtx.clip();
  draftCtx.clearRect(left, top, right - left, bottom - top);
  draftCtx.drawImage(mask, left, top, right - left, bottom - top, left, top, right - left, bottom - top);
  draftCtx.setTransform(sx, 0, 0, sy, 0, 0);
  draftCtx.globalCompositeOperation = 'source-in';
  draftCtx.globalAlpha = alpha * (family === 'marker' ? .9 : family === 'paintbrush' ? .85 : 1);
  draftCtx.fillStyle = brush.texture ? grain(draftCtx, rgb, family === 'mechanical') : colorCss(rgb);
  draftCtx.fillRect(left / sx, top / sy, (right - left) / sx, (bottom - top) / sy);
  draftCtx.restore();
}
