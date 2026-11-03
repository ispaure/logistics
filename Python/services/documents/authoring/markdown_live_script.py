"""WebView adapter for the shared live Markdown syntax rules."""

LIVE_SCRIPT = r'''
const livePatterns = LIVE_PATTERNS;
LIVE_ACTIVE
// Visibility uses a separate stylesheet: moving the caret must never change
// editable HTML, source, dirty state, or undo snapshots.
const markerStyle = document.createElement('style');
markerStyle.nonce = document.currentScript.nonce; document.head.append(markerStyle);
let markerId = 0;
const markerIntervals = new WeakMap();
function refreshSyntaxVisibility() {
    const selection = getSelection();
    const range = selection.rangeCount ? selection.getRangeAt(0) : null;
    const visible = [];
    for (const marker of root.querySelectorAll('.live-marker')) {
        const interval = markerIntervals.get(marker);
        if (!interval || !range) continue;
        const {section, start, end} = interval;
        if (!range.intersectsNode(section)) continue;
        const first = section.contains(range.startContainer) ? textOffset(section, range.startContainer, range.startOffset) : -Infinity;
        const last = section.contains(range.endContainer) ? textOffset(section, range.endContainer, range.endOffset) : Infinity;
        if (syntaxActive(start, end, first, last)) visible.push('[data-live-marker="' + marker.dataset.liveMarker + '"]');
    }
    markerStyle.textContent = visible.length ? '#document ' + visible.join(',#document ') + '{font-size:inherit}' : '';
}
document.addEventListener('selectionchange', refreshSyntaxVisibility);
const inlinePatterns = livePatterns.inline.map(pattern => new RegExp(pattern, 'gu'));
const headingPattern = new RegExp(livePatterns.heading);
const originalText = new WeakMap();
const originalRich = new WeakSet(root.querySelectorAll('strong,b,em,i,code'));
for (const section of root.children) {
    const walker = document.createTreeWalker(section, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) if (!walker.currentNode.parentElement.closest('[data-live-source]'))
        originalText.set(walker.currentNode, walker.currentNode.data);
}
// Text alone gives an empty paragraph the same offset as the previous line.
// Count structural boundaries too, so restoring decorations/history never moves
// a caret backwards across Enter or Shift+Enter.
const caretBlocks = new Set(['P','DIV','LI','H1','H2','H3','H4','H5','H6','PRE','BLOCKQUOTE','TD','TH']);
function caretPrefix(node, section) {
    return node !== section && caretBlocks.has(node.nodeName) ? 1 : 0;
}
function caretSize(node, section) {
    if (node.nodeType === Node.TEXT_NODE) return node.length;
    if (node.nodeName === 'BR') return 1;
    return caretPrefix(node, section) + [...node.childNodes].reduce((size, child) => size + caretSize(child, section), 0);
}
function textOffset(section, node, offset) {
    let value = node.nodeType === Node.TEXT_NODE ? offset : caretPrefix(node, section) +
        [...node.childNodes].slice(0, offset).reduce((size, child) => size + caretSize(child, section), 0);
    // A range around a whole block starts before its element; normalize it to
    // the equivalent editable position inside the leading block(s).
    if (node.nodeType !== Node.TEXT_NODE) {
        let child = node.childNodes[offset];
        while (child && caretPrefix(child, section)) {
            value += caretPrefix(child, section); child = child.firstChild;
        }
    }
    while (node !== section) {
        const parent = node.parentNode;
        for (let previous = node.previousSibling; previous; previous = previous.previousSibling)
            value += caretSize(previous, section);
        value += caretPrefix(parent, section); node = parent;
    }
    return value;
}
function textPosition(section, offset) {
    function locate(node) {
        if (node.nodeType === Node.TEXT_NODE) {
            if (offset <= node.length) return [node, offset];
            offset -= node.length; return null;
        }
        if (node.nodeName === 'BR') {
            if (offset <= 1) return [node.parentNode, [...node.parentNode.childNodes].indexOf(node) + offset];
            offset--; return null;
        }
        if (caretPrefix(node, section)) {
            if (offset <= 1) return [node, 0];
            offset--;
        }
        for (const child of node.childNodes) {
            const found = locate(child); if (found) return found;
        }
        return null;
    }
    return locate(section) || [section, section.childNodes.length];
}
function prepareBlockStyle(selection) {
    const range = selection.getRangeAt(0);
    // A live heading is a paragraph carrying its source prefix. Consume that
    // prefix before asking the browser for a semantic block, otherwise the
    // heading style and serialized '#' accumulate. DOM ranges keep the selected
    // body (including inline formatting and Unicode) as the prefix is removed.
    for (const block of root.querySelectorAll('[data-live-heading]')) {
        const body = document.createRange(); body.selectNodeContents(block);
        const selected = range.collapsed ? block.contains(range.startContainer) :
            range.compareBoundaryPoints(Range.END_TO_START, body) < 0 &&
            range.compareBoundaryPoints(Range.START_TO_END, body) > 0;
        if (!selected) continue;
        const heading = headingPattern.exec(block.textContent);
        delete block.dataset.liveHeading;
        if (!heading) continue;
        const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
        let remaining = heading[0].length;
        const prefix = document.createRange(); prefix.setStart(block, 0);
        while (walker.nextNode()) {
            if (remaining <= walker.currentNode.length) {
                prefix.setEnd(walker.currentNode, remaining); prefix.deleteContents(); break;
            }
            remaining -= walker.currentNode.length;
        }
    }
}
function renderTypedMarkup(target=null) {
    const selection = getSelection();
    if (!target && (!selection.rangeCount || !editableRange(selection.getRangeAt(0)))) return;
    const range = target ? null : selection.getRangeAt(0);
    const element = target || (range.startContainer.nodeType === Node.TEXT_NODE ? range.startContainer.parentElement : range.startContainer);
    const section = element.closest('section');
    let first = range ? textOffset(section, range.startContainer, range.startOffset) : 0;
    let last = range ? textOffset(section, range.endContainer, range.endOffset) : 0;
    // Preserve source offsets while rebuilding display spans. WebView undo
    // cannot track these decorations; the bounded section history below owns it.
    // Native toolbar commands introduce rich elements. Materialize their
    // source too, so toolbar formatting follows the same visibility rules.
    if (applyingCommand) for (const rich of [...section.querySelectorAll('strong,b,em,i,code')]) {
        if (!rich.isConnected || originalRich.has(rich) || rich.closest('pre,[contenteditable=false]')) continue;
        const live = document.createElement('span'); live.dataset.liveSource = '';
        const copy = rich.cloneNode(true);
        if (rich.nodeName !== 'CODE') {
            const originalNodes = document.createTreeWalker(rich, NodeFilter.SHOW_TEXT);
            const copiedNodes = document.createTreeWalker(copy, NodeFilter.SHOW_TEXT);
            while (originalNodes.nextNode() && copiedNodes.nextNode()) {
                const text = originalNodes.currentNode;
                if (originalText.get(text) === text.data && !text.parentElement.closest('[data-live-source]'))
                    copiedNodes.currentNode.data = inline(text);
            }
        }
        const source = inline(copy, true), base = textOffset(section, rich, 0);
        const size = caretSize(rich, section), opening = ['STRONG','B'].includes(rich.nodeName) ? 2 : 1;
        const delta = source.length - size;
        const remap = offset => offset < base ? offset : offset <= base + size ? offset + opening : offset + delta;
        first = remap(first); last = remap(last);
        live.textContent = source; rich.replaceWith(live);
    }
    for (const decoration of section.querySelectorAll('[data-live-decoration]')) {
        decoration.removeAttribute('data-live-decoration');
        decoration.removeAttribute('data-live-marker');
        decoration.classList.remove('live-code', 'live-bold', 'live-italic', 'live-marker');
        if (!decoration.className) decoration.removeAttribute('class');
        if (!decoration.attributes.length) decoration.replaceWith(...decoration.childNodes);
    }
    for (const live of section.querySelectorAll('[data-live-source]')) {
        live.removeAttribute('data-live-source');
        if (!live.attributes.length) live.replaceWith(...live.childNodes);
    }
    section.normalize();
    const walker = document.createTreeWalker(section, NodeFilter.SHOW_TEXT);
    const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
        if (node.parentElement.closest('pre,code,[contenteditable=false]')) continue;
        if (originalText.get(node) === node.data && !node.parentElement.closest('[data-live-source]')) continue;
        const original = node.parentElement.closest('[data-live-source]') ? undefined : originalText.get(node);
        if (original !== undefined) {
            const value = node.data;
            let prefix = 0, suffix = 0;
            while (prefix < original.length && prefix < value.length && original[prefix] === value[prefix]) prefix++;
            while (suffix < original.length - prefix && suffix < value.length - prefix &&
                original[original.length - 1 - suffix] === value[value.length - 1 - suffix]) suffix++;
            // Imported literal punctuation was already escaped in Markdown.
            // Preserve that intent when new syntax is typed into the same node.
            const start = textOffset(section, node, 0), offsets = [0];
            let protectedText = '';
            for (let i=0; i<value.length; i++) {
                if ((i < prefix || i >= value.length - suffix) && /[\\*_`\[\]<>]/.test(value[i])) protectedText += '\\';
                protectedText += value[i]; offsets.push(protectedText.length);
            }
            const remap = offset => offset <= start ? offset : offset <= start + value.length ?
                start + offsets[offset - start] : offset + protectedText.length - value.length;
            first = remap(first); last = remap(last); node.data = protectedText;
        }
        const text = node.data, spans = liveSpans(text);
        const base = textOffset(section, node, 0);
        const block = node.parentElement.closest('p,div,li,h1,h2,h3,h4,h5,h6');
        const heading = block && !block.closest('h1,h2,h3,h4,h5,h6') &&
            block.firstChild === node && headingPattern.exec(text);
        if (heading) block.dataset.liveHeading = heading[1].length;
        if (!spans.length && !heading) {
            // Keep a source wrapper even for incomplete/escaped syntax so the
            // serializer does not escape what the user intentionally typed.
            const live = document.createElement('span'); live.dataset.liveSource = '';
            live.textContent = text; node.replaceWith(live); continue;
        }
        const live = document.createElement('span'); live.dataset.liveSource = '';
        const boundaries = new Set([0, text.length]);
        if (heading) boundaries.add(heading[0].length);
        for (const span of spans) for (const offset of [span.start, span.start + span.marker.length,
                span.end - span.marker.length, span.end]) boundaries.add(offset);
        const offsets = [...boundaries].sort((a,b) => a-b);
        for (let part = 0; part < offsets.length - 1; part++) {
            const i = offsets[part], end = offsets[part + 1];
            const char = document.createElement('span'); char.dataset.liveDecoration = ''; char.textContent = text.slice(i, end);
            const active = spans.filter(span => span.start <= i && i < span.end);
            let marker = Boolean(heading && i < heading[0].length);
            for (const span of active) {
                if (i < span.start + span.marker.length || i >= span.end - span.marker.length) marker = true;
                else if (span.marker.startsWith('`')) char.classList.add('live-code');
                else {
                    if (span.marker.length >= 2) char.classList.add('live-bold');
                    if ([1, 3].includes(span.marker.length)) char.classList.add('live-italic');
                }
            }
            if (marker) {
                char.classList.add('live-marker'); char.dataset.liveMarker = ++markerId;
                const owners = active.filter(span => i < span.start + span.marker.length || i >= span.end - span.marker.length);
                markerIntervals.set(char, {section,
                    start:base + (heading && i < heading[0].length ? 0 : Math.min(...owners.map(span => span.start))),
                    end:base + (heading && i < heading[0].length ? textOffset(section, block, block.childNodes.length) - base : Math.max(...owners.map(span => span.end)))});
            }
            live.append(char);
        }
        node.replaceWith(live);
    }
    for (const block of section.querySelectorAll('[data-live-heading]')) {
        const heading = headingPattern.exec(block.textContent);
        if (!heading || block.closest('pre,code,h1,h2,h3,h4,h5,h6')) delete block.dataset.liveHeading;
        else block.dataset.liveHeading = heading[1].length;
    }
    if (!range) { refreshSyntaxVisibility(); return; }
    const restored = document.createRange();
    restored.setStart(...textPosition(section, first)); restored.setEnd(...textPosition(section, last));
    selection.removeAllRanges(); selection.addRange(restored); savedRange = restored.cloneRange();
    refreshSyntaxVisibility();
}
// beforeinput works for soft keyboards and hardware keyboards alike, unlike
// keydown. Keep the interior selected so a second '*' upgrades italic to bold.
root.addEventListener('beforeinput', event => {
    if (event.isComposing || event.inputType !== 'insertText' ||
        !livePatterns.selection.includes(event.data)) return;
    const selection = getSelection();
    if (!selection.rangeCount || selection.isCollapsed || !editableRange(selection.getRangeAt(0))) return;
    const range = selection.getRangeAt(0), marker = event.data;
    const element = range.startContainer.nodeType === Node.TEXT_NODE ? range.startContainer.parentElement : range.startContainer;
    if (element.closest('pre,code,[contenteditable=false]')) return;
    const section = element.closest('section');
    const first = textOffset(section, range.startContainer, range.startOffset), text = selection.toString();
    event.preventDefault();
    document.execCommand('insertText', false, marker + text + marker);
    const wrapped = document.createRange();
    wrapped.setStart(...textPosition(section, first + marker.length));
    wrapped.setEnd(...textPosition(section, first + marker.length + text.length));
    selection.removeAllRanges(); selection.addRange(wrapped);
    renderTypedMarkup(); rememberEdit(); publish(); scheduleCaretReveal();
});

// DOM decoration replaces text nodes referenced by native undo records. Retain
// section snapshots explicitly so typing, formatting and IME commits stay undoable.
for (const section of root.children) if (section.querySelector('[data-live-source]')) renderTypedMarkup(section);
const undoEdits = [], redoEdits = [];
const sectionStates = new Map([...root.children].map(section => [section, captureState(section)]));
let historyBytes = 0;
function captureState(section) {
    const selection = getSelection(), range = selection.rangeCount && selection.getRangeAt(0);
    const snapshot = section.cloneNode(true);
    for (const marker of snapshot.querySelectorAll('[data-live-marker]')) marker.removeAttribute('data-live-marker');
    return {html:snapshot.innerHTML,
        first:range && section.contains(range.startContainer) ? textOffset(section, range.startContainer, range.startOffset) : 0,
        last:range && section.contains(range.endContainer) ? textOffset(section, range.endContainer, range.endOffset) : 0};
}
root.addEventListener('beforeinput', () => {
    const selection = getSelection();
    if (!selection.rangeCount || !editableRange(selection.getRangeAt(0))) return;
    const node = selection.anchorNode, element = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
    const section = element.closest('section'), state = sectionStates.get(section);
    const current = captureState(section);
    if (state && state.html === current.html) sectionStates.set(section, current);
}, true);
function rememberEdit() {
    for (const section of root.children) {
        const before = sectionStates.get(section), after = captureState(section);
        if (before.html === after.html) continue;
        undoEdits.push({section, before, after}); redoEdits.length = 0;
        historyBytes += 2 * (before.html.length + after.html.length);
        sectionStates.set(section, after);
        while (undoEdits.length > 1 && (undoEdits.length > 100 || historyBytes > 8 * 1024 * 1024)) {
            const removed = undoEdits.shift(); historyBytes -= 2 * (removed.before.html.length + removed.after.html.length);
        }
    }
}
function editHistory(redo=false) {
    const edit = (redo ? redoEdits : undoEdits).pop();
    if (!edit) return;
    (redo ? undoEdits : redoEdits).push(edit);
    const state = redo ? edit.after : edit.before;
    edit.section.innerHTML = state.html; sectionStates.set(edit.section, state);
    const walker = document.createTreeWalker(edit.section, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
        if (!walker.currentNode.parentElement.closest('[data-live-source]'))
            originalText.set(walker.currentNode, walker.currentNode.data);
    }
    edit.section.focus({preventScroll:true});
    const range = document.createRange();
    range.setStart(...textPosition(edit.section, state.first)); range.setEnd(...textPosition(edit.section, state.last));
    const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
    savedRange = range.cloneRange(); renderTypedMarkup(); sectionStates.set(edit.section, captureState(edit.section)); publish(); scheduleCaretReveal();
}
root.addEventListener('beforeinput', event => {
    if (['historyUndo', 'historyRedo'].includes(event.inputType)) {
        event.preventDefault(); editHistory(event.inputType === 'historyRedo');
    }
});
root.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && !event.altKey) {
        const key = event.key.toLowerCase();
        if (key === 'z' || key === 'y') { event.preventDefault(); editHistory(key === 'y' || event.shiftKey); }
        else if (key === 'b' || key === 'i') { event.preventDefault(); command(key === 'b' ? 'bold' : 'italic'); }
    }
});
'''
