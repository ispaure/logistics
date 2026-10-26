"""Original offline SVG drawing glyphs shared by notebook presentations."""

ICON_SCRIPT = r'''
const glyphs={
pen:'<path d="m5 19 2-6L17 3l4 4-10 10-6 2Zm2-6 4 4M15 5l4 4M4 21h16"/>',
erase:'<path d="m4 13 9-9a2 2 0 0 1 3 0l5 5a2 2 0 0 1 0 3l-8 8H9l-5-5a1.5 1.5 0 0 1 0-2Zm4-4 9 8M13 20h9"/>',
select:'<path d="M7 4C3 5 2 9 4 12s8 5 13 2 4-8 0-10C14 2 10 3 7 4Z" stroke-dasharray="2.5 3"/><path d="m12 12 2 9 2-4 4-2-8-3Z"/>',
undo:'<path d="m8 5-5 5 5 5M3 10h10a7 7 0 0 1 7 7v2"/>',
redo:'<path d="m16 5 5 5-5 5m5-5H11a7 7 0 0 0-7 7v2"/>',
library:'<rect x="3" y="4" width="7" height="16" rx="1.5"/><path d="M14 4h5l3 15-6 1-3-15ZM6 8h1M6 16h1"/>',
save:'<path d="M5 3h12l4 4v14H3V3h2Zm2 0v7h10V3M7 21v-7h10v7"/>',
export:'<path d="M12 15V3m-4 4 4-4 4 4M4 14v6h16v-6"/>',
more:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
layers:'<path d="m12 3 10 5-10 5L2 8l10-5ZM2 12l10 5 10-5M2 16l10 5 10-5"/>',
panel:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16m3-11v6"/>',
prev:'<path d="m14 6-6 6 6 6"/>',next:'<path d="m10 6 6 6-6 6"/>',plus:'<path d="M12 5v14M5 12h14"/>'};
const nibs={
'Fineliner':'<path d="M9 3h6v11l-3 6-3-6V3Zm0 5h6m-6 6h6m-3 6v2"/>',
'Ballpoint':'<path d="M10 3h4l2 5-2 9-2 4-2-4-2-9 2-5Zm0 0V1m-2 7h8m-6 9h4"/><circle cx="12" cy="22" r=".6"/>',
'Pencil':'<path d="m8 3 7-1 3 14-3 6-5-4L8 3Zm2 4 6-1m-6 12 8-2m-3 6-1-4m-2-11 2 9"/>',
'Mechanical pencil':'<path d="M10 4h5v11l-2.5 5-2.5-5V4Zm-1 0V2h7v2m-6 7h5m-5 4h5m-2.5 5v3M17 5v6"/>',
'Marker':'<path d="M7 2h10v12l-3 3v4h-4v-4l-3-3V2Zm0 8h10m-7 7h4m-4 4h4"/>',
'Paintbrush':'<path d="M11 13C10 8 13 2 15 1c1 4 0 9-1 12m-3 0 3 1c3 5-1 9-7 8 3-2-1-6 4-9Z"/><path d="m10 17 1 3"/>',
'Calligraphy':'<path d="m7 3 10 2-3 15-6-1L7 3Zm0 6 9 2m-8 8 6 1m-5-4 6 1M10 4l-1 5"/>',
'Shader':'<path d="M6 3h12v10l-3 3v5H9v-5l-3-3V3Zm0 7h12m-9 6h6m-6 3h6"/><path d="M4 22h16" stroke-dasharray="1 2"/>',
'Highlighter':'<path d="M7 2h10v11l-2 3v4l-6 2v-6l-2-3V2Zm0 9h10m-8 5h6m-6 4 6-2"/>'};
function icon(path){return '<svg viewBox="0 0 24 24" aria-hidden="true">'+path+'</svg>'}
'''
