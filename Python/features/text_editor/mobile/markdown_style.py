"""Responsive writing surface; formatting overlays never resize the document."""

READING_CSS = '''
html body{max-width:800px;margin:0 auto;padding:20px 24px 32px;box-sizing:border-box;line-height:1.65}
html body h1{font-size:2em}html body h2{font-size:1.55em}html body h3{font-size:1.25em}
html body h1,html body h2,html body h3{letter-spacing:-.02em}
html body pre{border:0;border-radius:12px;background:var(--surface,ButtonFace)}
html body blockquote{border-left-color:var(--accent,GrayText)}
@media(max-width:380px){html body{padding:16px}}
'''

EDITOR_CSS = r'''
:root { color-scheme: light dark; --toolbar-height: 56px; }
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; overflow: hidden; }
body {
    display: flex; flex-direction: column; min-height: 0;
    font-family: -apple-system,BlinkMacSystemFont,sans-serif; line-height: 1.65;
    background: var(--window, Canvas); color: var(--text, CanvasText);
    -webkit-text-size-adjust: 100%;
}
button, select, input, summary { font: inherit; color: inherit; min-height: 44px; }
button, summary {
    border: 0; border-radius: 10px; background: transparent; cursor: pointer;
    touch-action: manipulation;
}
button:active, summary:active, button[aria-pressed=true] {
    background: var(--hover, ButtonFace); color: var(--accent, Highlight);
}
button:focus-visible, summary:focus-visible, select:focus-visible {
    outline: 2px solid var(--accent, Highlight); outline-offset: -2px;
}
button[disabled] { opacity: .45; cursor: default; }
nav {
    flex: 0 0 var(--toolbar-height); display: flex; align-items: center; gap: 2px;
    padding: 4px 8px; z-index: 2; background: var(--window, Canvas);
    border-bottom: 1px solid var(--border, ButtonFace);
}
.mode-label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: .8em; font-weight: 600; padding: 0 8px; }
.icon-button { width: 44px; padding: 0; display: inline-flex; align-items: center; justify-content: center; }
.icon-button svg, summary svg { width: 20px; height: 20px; pointer-events: none; }
nav details { margin-left: auto; }
summary { display: flex; align-items: center; justify-content: center; gap: 6px; padding: 0 10px; list-style: none; font-size: .85em; font-weight: 600; }
summary::-webkit-details-marker { display: none; }
details[open] summary { background: var(--surface, ButtonFace); }
.format-menu {
    position: fixed; top: var(--toolbar-height); right: 8px; left: 8px;
    max-width: 480px; margin-left: auto; max-height: calc(100% - var(--toolbar-height) - 8px);
    overflow: auto; overscroll-behavior: contain; display: flex; flex-wrap: wrap;
    align-content: flex-start; align-items: center; gap: 6px; padding: 12px;
    border: 1px solid var(--border, GrayText); border-radius: 16px;
    background: var(--surface, Canvas); box-shadow: 0 8px 28px #0003;
}
.format-menu label { display: flex; align-items: center; gap: 8px; width: 100%; font-size: .85em; }
.format-menu select { flex: 1; min-width: 0; border-radius: 8px; padding: 0 8px; background: var(--window, Canvas); }
.format-menu .icon-button { background: var(--window, Canvas); }
.compact-formatting { display: none; }
#notice { flex-shrink: 0; margin: 0; padding: 6px 12px; font-size: .85em; background: var(--surface, Canvas); }
#notice:empty { display: none; }
#document {
    flex: 1; min-height: 0; width: 100%; max-width: 800px; margin: 0 auto;
    overflow: auto; overflow-wrap: anywhere; overscroll-behavior: contain;
    scroll-padding: 12px 0; padding: 20px 24px 32px;
    display: flex; flex-direction: column; -webkit-overflow-scrolling: touch;
}
section { flex-shrink: 0; outline: none; min-height: 1em; }
section[contenteditable=true]:last-child { flex: 1; min-height: 6em; }
section:empty { display: none; }
#document h1, #document h2, #document h3, #document h4, #document h5, #document h6 {
    line-height: 1.25; letter-spacing: -.02em; margin: .6em 0 .4em; font-weight: 700;
}
#document h1 { font-size: 2em; } #document h2 { font-size: 1.55em; }
#document h3 { font-size: 1.25em; } #document h4 { font-size: 1.1em; }
#document h5, #document h6 { font-size: 1em; }
#document p { margin: .35em 0 .85em; }
#document p, #document li { text-align: var(--logistics-text-align, start); }
#document ul, #document ol { margin: .4em 0 .9em; padding-left: 1.5em; }
#document li > ul, #document li > ol { margin-bottom: .2em; }
#document a { color: var(--accent, LinkText); text-underline-offset: .15em; }
#document blockquote { margin: .5em 0 1em; border-left: 3px solid var(--accent, GrayText); padding: .1em 1em; }
#document pre { white-space: pre; overflow-x: auto; padding: 12px; border-radius: 12px; background: var(--surface, ButtonFace); }
#document code { font-family: ui-monospace, monospace; font-size: .88em; }
#document :not(pre) > code { padding: .12em .3em; border-radius: 4px; background: var(--surface, ButtonFace); }
#document img { max-width: 100%; height: auto; border-radius: 8px; }
#document table { border-collapse: collapse; max-width: 100%; display: block; overflow-x: auto; margin: .5em 0 1em; }
#document td, #document th { border: 1px solid var(--border, GrayText); padding: 8px 12px; min-width: 5em; }
#document th { background: var(--surface, ButtonFace); text-align: start; }
section[data-source-only] { border-left: 2px solid var(--border, GrayText); padding-left: 12px; }
section[data-source-only]::after { content: 'Edit this block in Source'; display: block; color: var(--text, CanvasText); font-size: .75em; margin-bottom: .8em; }
p[data-editor-boundary] { margin: 0 !important; min-height: .5em; line-height: .5em; }
dialog {
    color: var(--text, CanvasText); background: var(--window, Canvas);
    border: 1px solid var(--border, GrayText); border-radius: 18px; padding: 20px;
    width: 380px; max-width: calc(100vw - 24px); max-height: calc(100% - 16px);
}
dialog[open] { display: flex; flex-direction: column; }
dialog::backdrop { background: #0006; }
dialog h2 { flex-shrink: 0; font-size: 1.1em; margin: 0 0 12px; }
.link-fields { min-height: 0; overflow: auto; }
dialog label, dialog input { display: block; width: 100%; }
dialog label { font-size: .85em; } dialog input { font-size: 16px; border: 1px solid var(--border, GrayText); border-radius: 8px; padding: 8px; background: var(--surface, Canvas); }
.dialog-actions { flex-shrink: 0; display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
.dialog-actions button { padding: 0 16px; background: var(--surface, ButtonFace); }
#apply-link { color: var(--accent, Highlight); font-weight: 600; }
#link-error { font-size: .8em; } #link-error:empty { display: none; }
@media (max-width: 380px) { .mode-label { display: none; } #document { padding: 16px; } }
@media (max-width: 360px) { summary span { display: none; } }
@media (max-height: 260px) {
    :root { --toolbar-height: 48px; } nav { padding: 0 4px; }
    #document { padding: 4px 12px 16px; }
    dialog { padding: 8px; } dialog h2 { display: none; }
    .dialog-actions { margin-top: 4px; }
}
'''
