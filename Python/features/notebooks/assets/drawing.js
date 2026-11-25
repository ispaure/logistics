// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

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
// On Android, repeatedly reading an accelerated mask into the draft and
// flattening that draft into the page can stall WebView's compositor.
const previewContext = state.software_ink_preview ? {willReadFrequently: true} : undefined;
const draft = $('draft'),
  draftCtx = draft.getContext('2d', previewContext);
const mask = document.createElement('canvas'),
  maskCtx = mask.getContext('2d', previewContext);
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
const intensityByBrush = new Map(Object.entries(state.brush_intensities || {}).map(([tool, value]) => [Number(tool), value]));
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

function saveWorkingBrush() {
  const {tool, color, width} = chosenInk();
  const brush = [tool, color, width];
  const pending = [...queue].reverse().find(action => action.op === 'working-brush');
  if ((pending?.brush ?? state.working_brush)?.join(',') !== brush.join(',')) send({op:'working-brush', brush});
}

function restoreWorkingBrush() {
  if (!state.working_brush) return;
  const [tool, color, width] = state.working_brush;
  $('tool').value = tool;
  brushOptions();
  $('color').value = color;
  $('width').value = width;
  if (!brushFor(tool).fixed_width) normalWidth = String(width);
}

function snapToTextControl() {
  const label = document.createElement('label'), input = document.createElement('input');
  input.type = 'checkbox';
  label.append(input, document.createTextNode('Snap to text'));
  input.onchange = () => {
    state.snap_to_text = input.checked;
    send({op: 'snap-to-text', enabled: input.checked});
  };
  return {
    label,
    update() {
      label.hidden = !state.can_snap_to_text || brushFor(Number($('tool').value)).family !== 'highlighter';
      input.checked = state.snap_to_text;
      input.disabled = !!(state.warning || state.read_only);
    }
  };
}

function fixedBrushPressure(tool) {
  const intensity = intensityByBrush.get(tool) ?? brushFor(tool).default_intensity;
  return intensity === undefined ? fallbackPressure : intensity / 100;
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
    [x, y, p, tilt = 0] = samples[i];
  let w = pressureWidth(brush, width, p);
  if (brush.tilt_widths) {
    const side = Math.max(0, Math.min(1, (tilt - brush.tilt_start) / (brush.tilt_full - brush.tilt_start)));
    w += (brush.tilt_widths[width - 1] - w) * side * side
  }
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

function darkNotebookPaper() {
  return document.body.classList.contains('dark-notebook-paper');
}

function inkColor(s, dark = false) {
  let rgba = s.color_rgba,
    hex = palette[s.color] || '#000000',
    rgb = rgba ? rgba.slice(0, 3) : s.tool === 18 && state.native_highlights[s.color] ? state.native_highlights[s.color].slice(0, 3) : [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
  if (dark && (rgb.every(value => value === 0) || rgb.every(value => value === 255)))
    rgb = rgb.map(value => 255 - value);
  else if (dark && brushFor(s.tool).family !== 'highlighter')
    rgb = state.dark_ink_colors?.[rgb.join(',')] || rgb;
  if ($('grayscale').checked) {
    let gray = Math.round(.2126 * rgb[0] + .7152 * rgb[1] + .0722 * rgb[2]);
    rgb = [gray, gray, gray]
  }
  return {
    rgb,
    alpha: (rgba ? rgba[3] / 255 : 1) * (dark && brushFor(s.tool).family === 'highlighter' ? .36 : 1)
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
const graphiteTileSize = 128;
const graphiteTooth = new Map();

function graphiteNoise(x, y, seed) {
  let value = Math.imul(x ^ seed, 0x45d9f3b) ^ Math.imul(y, 0x27d4eb2d);
  value = Math.imul(value ^ (value >>> 16), 0x45d9f3b);
  return ((value ^ (value >>> 16)) >>> 0) / 4294967296
}

function paperRelief(cells, seed) {
  const grid = Array.from({length: cells * cells}, (_, i) =>
    graphiteNoise(i % cells, Math.floor(i / cells), seed));
  const spacing = graphiteTileSize / cells;
  return (x, y) => {
    const col = Math.floor(x / spacing), row = Math.floor(y / spacing);
    const nextCol = (col + 1) % cells, nextRow = (row + 1) % cells;
    const fx = (x % spacing) / spacing, fy = (y % spacing) / spacing;
    const sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
    const top = grid[row * cells + col] * (1 - sx) + grid[row * cells + nextCol] * sx;
    const bottom = grid[nextRow * cells + col] * (1 - sx) + grid[nextRow * cells + nextCol] * sx;
    return top * (1 - sy) + bottom * sy;
  };
}

function graphiteRelief(mechanical) {
  if (graphiteTooth.has(mechanical)) return graphiteTooth.get(mechanical);
  // Fine paper tooth keeps broad pencil shading even while preserving small
  // bare pores at firm pressure.
  const side = graphiteTileSize, heights = new Uint8ClampedArray(side * side);
  const fine = new Uint8ClampedArray(side * side);
  const coarse = paperRelief(8, 827);
  const clumps = paperRelief(32, mechanical ? 173 : 419);
  const pores = paperRelief(64, mechanical ? 641 : 263);
  for (let y = 0; y < side; y++) {
    for (let x = 0; x < side; x++) {
      const grit = graphiteNoise(x, y, mechanical ? 3407 : 1009);
      const pore = pores(x, y);
      const relief = mechanical
        ? .08 * coarse(x, y) + .34 * clumps(x, y) + .36 * pore + .22 * grit
        : .04 * coarse(x, y) + .21 * clumps(x, y) + .43 * pore + .32 * grit;
      // Deep, small pores remain visible inside a firmly drawn stroke.
      const pit = mechanical ? Math.max(0, .14 - grit) * 1.25
        : Math.max(0, .32 - (.55 * grit + .45 * pore)) * 3.1;
      const index = y * side + x;
      heights[index] = (relief - pit) * 255;
      fine[index] = .75 * 255 * graphiteNoise(x, y, mechanical ? 1937 : 2503) + .25 * heights[index];
    }
  }
  const tooth = {heights, fine};
  graphiteTooth.set(mechanical, tooth);
  return tooth;
}

function graphiteLevel(pressure) {
  // Quantize after native pressure rounding so saved and live ink use the
  // same tile.
  return Math.round(Math.round(pressure * 255) * 32 / 255);
}

function grain(target, rgb, mechanical, pressure = .5, edge = false) {
  const level = graphiteLevel(pressure);
  const key = rgb.join(',') + ':' + Number(mechanical) + ':' + level + ':' + Number(edge);
  if (grainCache.has(key)) {
    const pattern = grainCache.get(key);
    grainCache.delete(key);
    grainCache.set(key, pattern);
    return pattern
  }
  const tile = document.createElement('canvas');
  const side = tile.width = tile.height = graphiteTileSize;
  const g = tile.getContext('2d'), image = g.createImageData(side, side);
  const {heights, fine} = graphiteRelief(mechanical), strength = level / 32;
  // Side shading uses the broader stored pencil footprint and a softer
  // contact transition. The fixed-width lead deposits more sharply.
  const lightContact = Math.max(0, 1 - ((strength - .46) / .34) ** 2) ** 2;
  // Mid-pressure strokes fill more of the paper tooth. Keep isolated
  // flecks at light pressure and leave firm deposits at full density.
  const midContact = Math.max(0, Math.min((strength - .57) / .23, (.9375 - strength) / .1375));
  const pencilContact = Math.max(0, Math.min((strength - .5) / .07, (.77 - strength) / .20));
  const engagement = strength + (mechanical ? .12 * midContact : .085 * midContact + .13 * pencilContact);
  const threshold = mechanical
    ? .91 - .69 * engagement ** 1.65 - .045 * lightContact
    : .85 - .64 * engagement ** 1.55 - .065 * lightContact;
  const transition = mechanical ? .10 : .16;
  // At light pressure, individual grains take dark flecks before broader
  // patches of paper take graphite. Their contribution fades as coverage grows.
  const fleckFade = Math.max(0, Math.min(1, (strength - .39) / .29));
  const fleckWeight = 1 - fleckFade ** 2 * (3 - 2 * fleckFade);
  const fleckThreshold = .98 - (mechanical ? .195 : .215) * Math.min(1, strength / .25);
  for (let i = 0; i < heights.length; i++) {
    const index = i * 4;
    const height = heights[i] / 255;
    const contact = Math.max(0, Math.min(1, (height - threshold) / transition));
    let opacity = contact * contact * (3 - 2 * contact) * (.68 + .32 * height);
    if (fleckWeight > 0) {
      const fleck = Math.max(0, Math.min(1, (fine[i] / 255 - fleckThreshold) / .025));
      opacity += (1 - opacity) * fleckWeight * fleck;
    }
    image.data[index] = rgb[0];
    image.data[index + 1] = rgb[1];
    image.data[index + 2] = rgb[2];
    // Leave disconnected flecks along the rim instead of a translucent outline.
    if (edge) opacity *= Math.max(0, Math.min(1, (fine[i] / 255 - .45) / .35));
    image.data[index + 3] = 255 * opacity;
  }
  g.putImageData(image, 0, 0);
  const pattern = target.createPattern(tile, 'repeat');
  // Pencil pressure changes which grains fill, at a fixed location and scale.
  // This keeps the grain continuous along a wide stroke with changing force.
  pattern.setTransform(new DOMMatrix().scale(mechanical ? .75 - .24 * midContact : .75));
  grainCache.set(key, pattern);
  if (grainCache.size > grainCacheLimit) grainCache.delete(grainCache.keys().next().value);
  return pattern
}

function graphitePaint(target, rgb, mechanical, pressure, edge = false) {
  // Keep individual grains sharp at writing size. At thumbnail scale, filtering
  // distributes subpixel flecks across the pixels they cover.
  const scale = target.getTransform().a;
  if ((!mechanical && scale >= .8) || (graphiteLevel(pressure) <= 10 && scale >= .5))
    target.imageSmoothingEnabled = false;
  return grain(target, rgb, mechanical, pressure, edge);
}

function graphiteEnvelope(target, brush, pressure, paint, textured = false) {
  const {family, display_width: baseWidth = 1} = brush;
  const strength = Math.max(0, Math.min(1, (pressure - .5) / (family === 'mechanical' ? .25 : .16)));
  if (!strength) {
    paint(baseWidth, false);
    return;
  }
  // The core carries most of the graphite. Individual flecks still extend
  // into the shoulder, where a firm stroke would otherwise have a hard edge.
  const alpha = target.globalAlpha;
  const shoulder = family === 'mechanical' ? .30 : .20;
  const width = family === 'mechanical' ? baseWidth : baseWidth * (1 - .035 * strength);
  target.globalAlpha = alpha * (1 - (textured ? .50 : .72) * strength);
  paint(width, textured);
  target.globalAlpha = alpha * (1 - .08 * strength);
  paint(width * (1 - shoulder * strength), false);
  target.globalAlpha = alpha;
}

function warmSelectedGraphite() {
  // Prewarm the default and fixed-input tiles before the first contact.
  if (active !== null) return;
  const tool = Number($('tool').value), brush = brushFor(tool);
  if (!brush.texture) return;
  const {rgb} = inkColor(nativeColor(tool, Number($('color').value)), darkNotebookPaper());
  const mechanical = brush.family === 'mechanical';
  grain(ctx, rgb, mechanical);
  if (state.brush_intensities) grain(ctx, rgb, mechanical, fixedBrushPressure(tool));
}
document.addEventListener('click', warmSelectedGraphite);
document.addEventListener('change', warmSelectedGraphite);

// Stored point arrays are immutable; full updates replace them. Weak ownership
// lets retired page/undo geometry go with its model instead of retaining a
// second document. Reuse the exact path rather than rebuilding every arc on
// each eraser acknowledgement, scroll/layout redraw or selection update.
const ribbonCache = new WeakMap();
function ribbon(target, p, widthScale) {
  let widths = ribbonCache.get(p);
  const cached = widths?.get(widthScale);
  if (cached) {
    target.fill(cached);
    return
  }
  const path = new Path2D();
  for (let i = 0; i < p.length; i++) {
    let b = p[i],
      r = b[3] * widthScale / 2;
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
      ar = a[3] * widthScale / 2;
    // Consistent winding makes the overlapping segment outlines one filled mask.
    path.moveTo(a[0] + nx * ar, a[1] + ny * ar);
    path.lineTo(a[0] - nx * ar, a[1] - ny * ar);
    path.lineTo(b[0] - nx * r, b[1] - ny * r);
    path.lineTo(b[0] + nx * r, b[1] + ny * r);
    path.closePath();
  }
  if (!widths) {
    widths = new Map();
    ribbonCache.set(p, widths);
  }
  if (widths.size === 2) widths.delete(widths.keys().next().value);
  widths.set(widthScale, path);
  target.fill(path);
}

function geometry(target, p, family, beforePoint = null, widthScale = 1) {
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
    target.lineWidth = p[0][3] * widthScale;
    target.beginPath();
    target.moveTo(p[0][0], p[0][1]);
    for (let i = 1; i < p.length; i++) target.lineTo(p[i][0], p[i][1]);
    target.stroke();
  } else ribbon(target, p, widthScale);
}

function graphiteTrail(target, points, rgb, brush, start = 0, contact = true) {
  const {family} = brush;
  const mechanical = family === 'mechanical', smoothing = target.imageSmoothingEnabled;
  const usePressure = (pressure, edge) => {
    target.imageSmoothingEnabled = smoothing;
    target.fillStyle = graphitePaint(target, rgb, mechanical, pressure, edge);
  };
  if (contact) {
    const pressure = graphiteLevel(points[0][2]) / 32;
    const point = [points[0]];
    graphiteEnvelope(target, brush, pressure, (width, edge) => {
      usePressure(pressure, edge);
      geometry(target, point, family, null, width);
    }, true);
  }
  let normal = null;
  // Carry the previous edge across frame boundaries. Adjacent segments
  // share an edge so dense input samples don't accumulate graphite there.
  for (let i = start; i > 0; i--) {
    const a = points[i - 1], b = points[start];
    const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (length) {
      normal = [(a[1] - b[1]) / length, (b[0] - a[0]) / length];
      break;
    }
  }
  for (let i = start + 1; i < points.length; i++) {
    const a = points[i - 1], b = points[i];
    const dx = b[0] - a[0], dy = b[1] - a[1], length = Math.hypot(dx, dy);
    if (!length) continue;
    const next = [-dy / length, dx / length];
    const [nx, ny] = normal || next;
    const pressure = graphiteLevel((Math.round(a[2] * 255) + Math.round(b[2] * 255)) / 510) / 32;
    graphiteEnvelope(target, brush, pressure, (width, edge) => {
      usePressure(pressure, edge);
      const ar = a[3] * width / 2, br = b[3] * width / 2;
      target.beginPath();
      target.moveTo(a[0] + nx * ar, a[1] + ny * ar);
      target.lineTo(a[0] - nx * ar, a[1] - ny * ar);
      target.lineTo(b[0] - next[0] * br, b[1] - next[1] * br);
      target.lineTo(b[0] + next[0] * br, b[1] + next[1] * br);
      target.closePath();
      target.fill();
    }, true);
    normal = next;
  }
  target.imageSmoothingEnabled = smoothing;
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

function line(s, target = ctx, outline = true, dark = target === ctx && darkNotebookPaper()) {
  let p = s.points;
  if (!p.length) return;
  let brush = brushFor(s.tool),
    family = brush.family,
    {
      rgb,
      alpha
    } = inkColor(s, dark);
  target.save();
  target.fillStyle = target.strokeStyle = colorCss(rgb);
  target.lineCap = 'round';
  target.lineJoin = 'round';
  target.globalAlpha = alpha;
  if (brush.texture) {
    const level = graphiteLevel(p[0][2]);
    if (p.some(point => graphiteLevel(point[2]) !== level)) {
      graphiteTrail(target, p, rgb, brush);
    } else {
      const pressure = level / 32;
      target.fillStyle = target.strokeStyle = graphitePaint(target, rgb, family === 'mechanical', pressure);
      graphiteEnvelope(target, brush, pressure, width => geometry(target, p, family, null, width));
    }
    target.restore();
    if (outline) strokeOutline(s, target);
    return;
  }
  if (family === 'highlighter') {
    target.globalCompositeOperation = dark ? 'screen' : 'multiply';
    target.lineCap = 'butt'
  }
  if (family === 'shader') {
    target.globalCompositeOperation = dark ? 'screen' : 'multiply';
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
  } else geometry(target, p, family, null, brush.display_width);
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

function paintTextHighlight(item, target, dark) {
  const rgb = dark && item.rgb.every(value => value === 0) ? [255, 255, 255] : item.rgb;
  target.save();
  target.globalAlpha = item.opacity;
  target.globalCompositeOperation = dark ? 'screen' : 'multiply';
  target.fillStyle = colorCss(rgb);
  target.beginPath();
  for (const rect of item.rectangles) target.rect(...rect);
  target.fill();
  target.restore();
}

function paintOrderedInk(items, target = ctx, showSelection = true, region = null, pictures = null, dark = false) {
  const colors = new Map(), runs = [];
  for (const item of items) {
    if (item.corners || item.rectangles || !item.points.length || brushFor(item.tool).family !== 'highlighter') {
      runs.push({item});
      continue;
    }
    const {rgb, alpha} = inkColor(item, dark), key = [...rgb, alpha].join(',');
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
      if (run.item.corners) {
        if (!pictures || pictures.has(run.item)) paintPicture(run.item, target, showSelection, pictures?.get(run.item));
      } else if (run.item.rectangles) paintTextHighlight(run.item, target, dark);
      else line(run.item, target, showSelection, dark);
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
    target.globalCompositeOperation = dark ? 'screen' : 'multiply';
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
const pagePreviewRenders = new WeakMap();

function refreshPagePreviews(container) {
  for (const image of container.querySelectorAll('img')) {
    const pending = pagePreviewRenders.get(image);
    if (pending) paintPagePreview(pending.page, image);
  }
}

async function paintPagePreview(page, image) {
  const dark = darkNotebookPaper();
  const render = {page};
  pagePreviewRenders.set(image, render);
  const preview = document.createElement('canvas');
  const scale = 288 / Math.max(page.width, page.height);
  preview.width = Math.max(1, Math.round(page.width * scale));
  preview.height = Math.max(1, Math.round(page.height * scale));
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
      const bounds = containedBackgroundBounds(artwork, page.pdf_paper || page.template_background_bounds ||
        {x: 0, y: 0, width: page.width, height: page.height});
      target.drawImage(artwork, bounds.x, bounds.y, bounds.width, bounds.height);
    } catch {
      // A failed background decode must still leave the ink visible.
    }
  }
  const pictures = new Map();
  for (const item of page.items) {
    if (!item.corners) continue;
    const picture = new Image();
    picture.src = item.src;
    try {
      await picture.decode();
    } catch {
      continue;
    }
    if (!image.isConnected) return;
    pictures.set(item, picture);
  }
  if (pagePreviewRenders.get(image) !== render) return;
  if (dark) invertPaper(target, page.width, page.height);
  paintOrderedInk(page.items, target, false, null, pictures, dark);
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
    } else if (liveGraphitePressure) {
      const {tool, color, width} = inkSettings;
      const {rgb, alpha} = inkColor(nativeColor(tool, color), darkNotebookPaper());
      const start = Math.max(0, previewCount - 1);
      let first = start;
      while (first > 0) {
        first--;
        if (points[first][0] !== points[start][0] || points[first][1] !== points[start][1]) break;
      }
      ctx.save();
      ctx.globalAlpha = alpha;
      graphiteTrail(ctx, strokePoints(points.slice(first), tool, width), rgb,
        brushFor(tool), start - first, previewCount === 0);
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
    } = inkColor(nativeColor(tool, color), darkNotebookPaper());
  draft.style.mixBlendMode = ['highlighter', 'shader'].includes(family)
    ? (darkNotebookPaper() ? 'screen' : 'multiply') : 'normal';
  maskCtx.save();
  maskCtx.fillStyle = maskCtx.strokeStyle = 'white';
  maskCtx.lineCap = family === 'highlighter' ? 'butt' : 'round';
  maskCtx.lineJoin = 'round';
  if (family === 'paintbrush') {
    maskCtx.filter = 'blur(.4px)';
    clipPaintbrush(maskCtx, pending)
  }
  if (brush.texture) {
    graphiteEnvelope(maskCtx, brush, graphiteLevel(points[0][2]) / 32,
      width => geometry(maskCtx, pending, family, beforePoint, width));
  } else geometry(maskCtx, pending, family, beforePoint, brush.display_width);
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
  draftCtx.fillStyle = brush.texture ? graphitePaint(draftCtx, rgb, family === 'mechanical', points[0][2]) : colorCss(rgb);
  draftCtx.fillRect(left / sx, top / sy, (right - left) / sx, (bottom - top) / sy);
  draftCtx.restore();
}
