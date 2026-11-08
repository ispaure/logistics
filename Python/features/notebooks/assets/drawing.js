const palette = state.palette;
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
  return state.brushes[aliases[tool] ?? tool] || state.brushes[17]
}

let normalWidth = '2', rememberBrushOptions = true;
const colorByBrush = new Map(Object.entries(state.brush_colors || {}).map(([tool, color]) => [Number(tool), color]));
let paletteBrush;
function brushOptions() {
  const tool = Number($('tool').value), brush = brushFor(tool), color = $('color');
  const previousColor = Number(color.value), previousWidth = $('width').value;
  if (rememberBrushOptions && paletteBrush !== undefined && color.value !== '') colorByBrush.set(paletteBrush, Number(color.value));
  options('color', brush.colors.map(id => Object.entries(state.colors).find(([name, value]) => value === id)));
  const rememberedColor = rememberBrushOptions ? colorByBrush.get(tool) : previousColor;
  color.value = brush.colors.includes(rememberedColor) ? rememberedColor : brush.colors[0];
  paletteBrush = tool;
  if (rememberBrushOptions && $('width').options.length > 1) normalWidth = $('width').value;
  options('width', brush.fixed_width ? [['Fixed', 1]] : Object.entries(state.widths));
  $('width').value = brush.fixed_width ? '1' : rememberBrushOptions ? normalWidth : previousWidth || '2';
  warmSelectedGraphite();
}

$('color').addEventListener('change', () => {
  const {tool, color} = chosenInk();
  if (!rememberBrushOptions || !brushFor(tool).colors.includes(color) || colorByBrush.get(tool) === color) return;
  colorByBrush.set(tool, color);
  if (state.brush_colors) send({op: 'brush-color', tool, color});
});

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
    tool,
    color: state.highlight_ids[color],
    color_rgba: null
  };
  if (tool === 23) return {
    tool,
    color: 9,
    color_rgba: state.shaders[color]
  };
  return {
    tool,
    color,
    color_rgba: null
  };
}

function pressureWidth(brush, width, pressure) {
  const curve = brush.pressure_widths;
  if (!curve) return brush.widths[width - 1] * (1 - brush.pressure + brush.pressure * Math.pow(pressure, brush.exponent));
  if (pressure <= curve[0][0]) return curve[0][1][width - 1];
  for (let i = 1; i < curve.length; i++) {
    let [start, before] = curve[i - 1], [end, after] = curve[i];
    if (pressure <= end) return before[width - 1] + (pressure - start) / (end - start) * (after[width - 1] - before[width - 1]);
  }
  return curve.at(-1)[1][width - 1];
}

function strokePoint(samples, i, tool, width) {
  let brush = brushFor(tool),
    [x, y, p] = samples[i];
  let w = pressureWidth(brush, width, p);
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
    rgb = rgba ? rgba.slice(0, 3) : s.tool === 18 && state.native_highlights[s.color] ? state.native_highlights[s.color].slice(0, 3) : [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
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
const grainCacheLimit = 24;
const graphiteMasks = new Map();

function graphiteNoise(x, y, seed) {
  let value = Math.imul(x ^ seed, 0x45d9f3b) ^ Math.imul(y, 0x27d4eb2d);
  value = Math.imul(value ^ (value >>> 16), 0x45d9f3b);
  return ((value ^ (value >>> 16)) >>> 0) / 4294967296
}

function graphiteMask(mechanical) {
  if (graphiteMasks.has(mechanical)) return graphiteMasks.get(mechanical);
  // Original graphite deposition, not a tablet texture or captured brush asset.
  // Fine tooth sits over a smooth paper field. The field wraps at its boundary,
  // so repeated tiles have no seam or the former tiny diagonal dot lattice.
  const side = 128, cells = 8, spacing = side / cells,
    seed = mechanical ? 173 : 419, mask = new Uint8ClampedArray(side * side),
    field = Array.from({length: cells * cells}, (_, i) => graphiteNoise(i % cells, Math.floor(i / cells), 827));
  for (let y = 0; y < side; y++) {
    const cy = Math.floor(y / spacing), fy = (y % spacing) / spacing,
      sy = fy * fy * (3 - 2 * fy);
    for (let x = 0; x < side; x++) {
      const cx = Math.floor(x / spacing), fx = (x % spacing) / spacing,
        sx = fx * fx * (3 - 2 * fx),
        top = field[cy * cells + cx] * (1 - sx) + field[cy * cells + (cx + 1) % cells] * sx,
        bottom = field[((cy + 1) % cells) * cells + cx] * (1 - sx) + field[((cy + 1) % cells) * cells + (cx + 1) % cells] * sx,
        paper = top * (1 - sy) + bottom * sy,
        tooth = graphiteNoise(x, y, seed),
        deposit = graphiteNoise(Math.floor(x / 2), Math.floor(y / 2), seed + 71);
      // Pencil leaves clustered paper gaps and a softer graphite body. A fine
      // mechanical lead stays dense and crisp, with only sparse tiny pinholes.
      const opacity = mechanical ? (tooth < .035 ? .32 : .74 + .2 * tooth + .06 * paper) :
        (deposit < .055 || tooth < .025 ? .22 : .16 + .42 * deposit + .24 * tooth + .16 * paper);
      mask[y * side + x] = Math.round(opacity * 255)
    }
  }
  graphiteMasks.set(mechanical, mask);
  return mask
}

function grain(target, rgb, mechanical) {
  const key = rgb.join(',') + ':' + Number(mechanical);
  if (grainCache.has(key)) {
    const pattern = grainCache.get(key);
    grainCache.delete(key);
    grainCache.set(key, pattern);
    return pattern
  }
  const tile = document.createElement('canvas');
  tile.width = tile.height = 128;
  const g = tile.getContext('2d'), image = g.createImageData(128, 128),
    mask = graphiteMask(mechanical);
  for (let i = 0; i < mask.length; i++) {
    const index = i * 4;
    image.data[index] = rgb[0];
    image.data[index + 1] = rgb[1];
    image.data[index + 2] = rgb[2];
    image.data[index + 3] = mask[i]
  }
  g.putImageData(image, 0, 0);
  const pattern = target.createPattern(tile, 'repeat');
  // A tile spans 64 native page units. Its origin stays on the page through
  // zoom and between incremental draft recoloring and completed-stroke paint.
  pattern.setTransform(new DOMMatrix().scale(.5));
  grainCache.set(key, pattern);
  if (grainCache.size > grainCacheLimit) grainCache.delete(grainCache.keys().next().value);
  return pattern
}

function warmSelectedGraphite() {
  // Selection, palette clicks and grayscale changes happen before a fresh pen
  // contact. Build their cached material here, never in a pointer-move hook.
  if (active !== null) return;
  const tool = Number($('tool').value), brush = brushFor(tool);
  if (!brush.texture) return;
  const {rgb} = inkColor(nativeColor(tool, Number($('color').value)));
  grain(ctx, rgb, brush.family === 'mechanical')
}
document.addEventListener('click', warmSelectedGraphite);
document.addEventListener('change', warmSelectedGraphite);

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
    let {nib_angle: angle, nib_ratio: ratio} = brushFor(21),
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

function line(s, target = ctx, outline = true) {
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
    target.globalCompositeOperation = 'multiply';
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
  target.restore();
  if (outline) strokeOutline(s, target);
}

function strokeOutline(s, target) {
  if (!selected.has(s.id) || mode === 'select') return;
  target.save();
  target.strokeStyle = '#2877cb';
  target.lineWidth = 2;
  const [left, top, right, bottom] = strokeBounds(s.points, 0);
  target.strokeRect(left - 5, top - 5, right - left + 10, bottom - top + 10);
  target.restore();
}

const highlightBoundsCache = new WeakMap();
function highlightBounds(points) {
  if (!highlightBoundsCache.has(points)) highlightBoundsCache.set(points, strokeBounds(points, 2));
  return highlightBoundsCache.get(points);
}

function strokeBounds(points, padding) {
  const bounds = [Infinity, Infinity, -Infinity, -Infinity];
  for (const [x, y, , width] of points) {
    const radius = width / 2 + padding;
    bounds[0] = Math.min(bounds[0], x - radius);
    bounds[1] = Math.min(bounds[1], y - radius);
    bounds[2] = Math.max(bounds[2], x + radius);
    bounds[3] = Math.max(bounds[3], y + radius);
  }
  return bounds;
}

function paintOrderedInk(items, target = ctx, showSelection = true, region = null) {
  const colors = new Map(), runs = [];
  for (const item of items) {
    if (item.corners || !item.points.length || brushFor(item.tool).family !== 'highlighter') {
      runs.push({item});
      continue;
    }
    const {rgb, alpha} = inkColor(item), key = [...rgb, alpha].join(',');
    const bounds = highlightBounds(item.points), previous = runs.at(-1);
    if (previous?.key === key) {
      previous.items.push(item);
      previous.bounds = previous.bounds.map((value, i) => i < 2 ? Math.min(value, bounds[i]) : Math.max(value, bounds[i]));
      continue;
    }
    if (!colors.has(key)) colors.set(key, []);
    const group = colors.get(key);
    const run = {items: [item], key, rgb, alpha, bounds, group, index: group.length};
    group.push(run);
    runs.push(run);
  }
  let scratch;
  const transform = target.getTransform();
  for (const run of runs) {
    if (run.item) {
      if (run.item.corners) paintPicture(run.item, target, showSelection);
      else line(run.item, target, showSelection);
      continue;
    }
    const [left, top, right, bottom] = run.bounds;
    const [l, t, r, b] = region || run.bounds;
    const x = Math.max(0, Math.floor(Math.max(left, l) * transform.a + transform.e));
    const y = Math.max(0, Math.floor(Math.max(top, t) * transform.d + transform.f));
    const width = Math.min(target.canvas.width, Math.ceil(Math.min(right, r) * transform.a + transform.e)) - x;
    const height = Math.min(target.canvas.height, Math.ceil(Math.min(bottom, b) * transform.d + transform.f)) - y;
    if (width <= 0 || height <= 0) continue;
    scratch ||= document.createElement('canvas');
    scratch.width = width;
    scratch.height = height;
    const g = scratch.getContext('2d');
    g.setTransform(transform.a, 0, 0, transform.d, transform.e - x, transform.f - y);
    g.strokeStyle = g.fillStyle = colorCss(run.rgb);
    g.lineCap = 'butt';
    g.lineJoin = 'round';
    const later = run.group.slice(run.index + 1).filter(next => intersects(next.bounds, run.bounds));
    const painted = [];
    // Rasterize the whole run as opaque coverage. Multiplying a path directly
    // can tint its self-intersections on WebKit, and punching out each adjacent
    // pass separately leaves antialiased seams inside the fill.
    for (const item of run.items) {
      if (painted.some(points => sameHighlightPath(points, item.points)) ||
          later.some(next => next.items.some(other => sameHighlightPath(other.points, item.points)))) continue;
      geometry(g, item.points, 'highlighter');
      painted.push(item.points);
    }
    // Across intervening ink/images the last run still owns the overlapping
    // tint, so marks above an earlier pass can be highlighted by a later one.
    g.globalCompositeOperation = 'destination-out';
    const masked = [];
    for (const next of later) {
      for (const item of next.items) {
        if (!intersects(highlightBounds(item.points), run.bounds) ||
            masked.some(points => sameHighlightPath(points, item.points))) continue;
        geometry(g, item.points, 'highlighter');
        masked.push(item.points);
      }
    }
    target.save();
    target.resetTransform();
    target.globalCompositeOperation = 'multiply';
    target.globalAlpha = run.alpha;
    target.drawImage(scratch, x, y);
    target.restore();
    if (showSelection) for (const item of run.items) strokeOutline(item, target);
  }
}

function intersects([l, t, r, b], [left, top, right, bottom]) {
  return l < right && r > left && t < bottom && b > top;
}

// The overview uses the same scene painter without any transient pen state,
// selection decoration or page zoom. Each card owns its asynchronous result.
async function paintPagePreview(page, image) {
  const preview = document.createElement('canvas');
  preview.width = 288;
  preview.height = Math.max(1, Math.round(preview.width * page.height / page.width));
  const target = preview.getContext('2d');
  target.setTransform(preview.width / page.width, 0, 0, preview.height / page.height, 0, 0);
  target.fillStyle = 'white';
  target.fillRect(0, 0, page.width, page.height);
  if (page.background) {
    const artwork = new Image();
    artwork.src = page.background;
    try {
      await artwork.decode();
      if (!image.isConnected) return;
      target.drawImage(artwork, 0, 0, page.width, page.height);
    } catch {
      // A failed template decode must still leave the ink visible.
    }
  }
  paintOrderedInk(page.items, target, false);
  image.src = preview.toDataURL();
}

function sameHighlightPath(points, other) {
  return points.length === other.length && points.every(([x, y, , width], i) => {
    const [otherX, otherY, , otherWidth] = other[i];
    return x === otherX && y === otherY && width === otherWidth;
  });
}

function activeHighlight() {
  if (!inkSettings || brushFor(inkSettings.tool).family !== 'highlighter' || !points.length) return null;
  const {tool, color, width} = inkSettings;
  return {tool, ...nativeColor(tool, color), points: strokePoints(points, tool, width)};
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
    ctx.globalCompositeOperation = ['highlighter', 'shader'].includes(family) ? 'multiply' : 'source-over';
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
    const highlight = activeHighlight();
    if (highlight) {
      const region = highlightBounds(highlight.points);
      const [left, top, right, bottom] = region;
      const transform = ctx.getTransform();
      const x = Math.floor(left * transform.a), y = Math.floor(top * transform.d);
      ctx.save();
      ctx.resetTransform();
      ctx.beginPath();
      ctx.rect(x, y, Math.ceil(right * transform.a) - x, Math.ceil(bottom * transform.d) - y);
      ctx.clip();
      ctx.setTransform(transform);
      draw(highlight, region);
      ctx.restore();
    } else preview(points.slice(Math.max(0, previewCount - 1)));
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
  draft.style.mixBlendMode = ['highlighter', 'shader'].includes(family) ? 'multiply' : 'normal';
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
