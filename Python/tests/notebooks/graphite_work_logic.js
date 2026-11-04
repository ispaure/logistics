// Operation-count checks for the actual renderer under a host V8 runtime.
// Canvas calls are instrumented stubs: timings describe JavaScript tile work,
// never raster throughput, Android SDK behavior or physical pen latency.
const vm = require('node:vm');
const {performance} = require('node:perf_hooks');

function checkGraphiteWork(source, state) {
  const counts = {tiles: 0, patterns: 0, imageUploads: 0, composites: []};
  class Matrix {scale() {return this}}
  class Path {moveTo() {} arc() {} lineTo() {} closePath() {}}
  class Canvas {
    constructor() {this.width = 1404; this.height = 1872; this.style = {}}
    getContext() {return this.context ||= context(this)}
  }
  function context(canvas) {
    return {canvas, save() {}, restore() {}, setTransform() {}, clearRect() {},
      fillRect() {}, beginPath() {}, rect() {}, clip() {}, fill() {}, stroke() {},
      moveTo() {}, lineTo() {}, arc() {}, strokeRect() {},
      createImageData(width, height) {return {data: new Uint8ClampedArray(width * height * 4)}},
      putImageData() {counts.imageUploads++},
      createPattern(tile) {counts.patterns++; return {tile, setTransform() {}}},
      drawImage(...args) {counts.composites.push(args.slice(1))}
    }
  }
  const canvas = new Canvas(), draft = new Canvas(), ctx = canvas.getContext('2d');
  const controls = {draft, grayscale: {checked: false}, tool: {value: '14'},
    color: {value: '0'}, width: {value: '2'}, layer: {value: 'synthetic'}};
  const listeners = {};
  const scope = {state, canvas, ctx, DOMMatrix: Matrix, Path2D: Path, performance,
    document: {createElement(name) {if (name !== 'canvas') throw Error(name); counts.tiles++; return new Canvas()},
      addEventListener(name, listener) {listeners[name] = listener}},
    $: id => controls[id], selected: new Set(), points: [], mode: 'ink', active: null};
  vm.createContext(scope);
  vm.runInContext(source, scope);
  const run = code => vm.runInContext(code, scope);
  const check = (value, message) => {if (!value) throw Error(message)};

  const tilesBefore = counts.tiles, patternsBefore = counts.patterns, uploadsBefore = counts.imageUploads;
  const start = performance.now();
  run('windowColdGraphite = grain(ctx,[0,0,0],false)');
  const coldTileJsMs = performance.now() - start;
  check(counts.tiles === tilesBefore + 1 && counts.patterns === patternsBefore + 1,
    'A cold graphite style must build exactly one tile and pattern');
  check(run('graphiteMasks.has(false)&&graphiteMasks.get(false).byteLength>0'),
    'The cold graphite style did not construct its material');
  check(counts.imageUploads <= uploadsBefore + 1, 'A cold tile uploaded its image repeatedly');
  const coldUploads = counts.imageUploads;
  const warmStart = performance.now();
  check(run('Array.from({length:1000},()=>grain(ctx,[0,0,0],false)).every(pattern=>pattern===windowColdGraphite)'),
    'Warm graphite lookups must reuse their cached pattern');
  const warm1000LookupsJsMs = performance.now() - warmStart;
  check(counts.tiles === tilesBefore + 1 && counts.patterns === patternsBefore + 1 &&
    counts.imageUploads === coldUploads, 'Warm lookups rebuilt or uploaded graphite');

  // Instrument generation only after the cold timing, so counters do not
  // inflate the observed hash-loop duration.
  run('windowNoiseCalls=0;windowOriginalNoise=graphiteNoise;graphiteNoise=(...args)=>{windowNoiseCalls++;return windowOriginalNoise(...args)}');
  const hashCalls = run('windowNoiseCalls'), colorStart = performance.now();
  run('grain(ctx,[48,74,224],false)');
  const newColorTileJsMs = performance.now() - colorStart;
  check(run('windowNoiseCalls') === hashCalls, 'A new RGB color rebuilt the paper/graphite alpha field');

  run('for(let i=0;i<160;i++)grain(ctx,[i,(i*37)%256,(i*91)%256],!!(i%2))');
  const retainedPatterns = run('grainCache.size');
  check(retainedPatterns <= 64, 'Arbitrary imported colors caused unbounded graphite cache growth');
  const retainedTileBytes = run('[...grainCache.values()].reduce((sum,pattern)=>sum+pattern.tile.width*pattern.tile.height*4,0)');
  check(retainedTileBytes <= 4 * 1024 * 1024, 'Graphite cache exceeds the 4 MiB raw-tile budget');

  const tailWork = [];
  for (const tool of [14, 13]) {
    scope.testTool = tool;
    controls.tool.value = String(tool);
    listeners.change();
    const warmedTiles = counts.tiles, warmedUploads = counts.imageUploads;
    run('points=Array.from({length:2000},(_,i)=>[30+i/20,60+Math.sin(i/20)*10,.6]);' +
      'inkSettings={tool:testTool,color:0,width:2,layer:"synthetic"};clearDraft();preview(points);' +
      'windowOriginalGeometry=geometry;windowTouched=0;geometry=(target,p,...rest)=>{windowTouched+=p.length;return windowOriginalGeometry(target,p,...rest)}');
    check(counts.tiles === warmedTiles && counts.imageUploads === warmedUploads,
      'The first preview allocated or uploaded its material after selection prewarming: ' + tool);
    const tileCount = counts.tiles, uploadCount = counts.imageUploads;
    run('(()=>{const previous=points.at(-1);points.push([131,65,.6]);preview([previous,points.at(-1)])})()');
    const touched = run('windowTouched');
    check(touched <= 2, 'A graphite move replayed stroke history: ' + tool);
    check(counts.tiles === tileCount && counts.imageUploads === uploadCount,
      'A warm graphite move rebuilt or uploaded its texture: ' + tool);
    run('windowTouched=0');
    counts.composites.length = 0;
    run('commitDraft(testTool)');
    check(run('windowTouched===0&&draftCount===0&&draftBounds===null'),
      'Pen-up replayed graphite geometry or retained its draft: ' + tool);
    check(counts.composites.length === 1, 'Pen-up must composite its draft once: ' + tool);
    const bounds = counts.composites[0];
    check(bounds.length === 8 && bounds[2] < canvas.width && bounds[3] < canvas.height,
      'Pen-up composited the entire page instead of the ink bounds: ' + tool);
    tailWork.push({tool, pointsInHistory: 2001, touched, penUpComposites: 1,
      compositeWidth: bounds[2], compositeHeight: bounds[3]});
    run('geometry=windowOriginalGeometry');
  }
  const alphaMaskBytes = run('[...graphiteMasks.values()].reduce((sum,mask)=>sum+mask.byteLength,0)');
  check(run('graphiteMasks.size<=2') && alphaMaskBytes <= 32768,
    'Color-independent graphite fields grew beyond the two-material budget');
  controls.color.value = '7';
  scope.active = 73;
  const activeTiles = counts.tiles;
  listeners.click();
  check(counts.tiles === activeTiles, 'UI warming generated a new texture during a pen contact');
  scope.active = null;
  return {success: true, coldTileJsMs, newColorTileJsMs, warm1000LookupsJsMs,
    retainedPatterns, retainedTileBytes, alphaMaskBytes, prewarmFirstPreviewAllocations: 0,
    tailWork, scope: 'Actual renderer JavaScript and operation counts with stub Canvas APIs; no raster or physical latency proof'};
}

module.exports = checkGraphiteWork;
if (require.main === module) {
  const fs = require('node:fs'), path = require('node:path');
  const state = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  console.log(JSON.stringify(checkGraphiteWork(fs.readFileSync(path.join(__dirname,
    '../../features/notebooks/assets/drawing.js'), 'utf8'), state)));
}
