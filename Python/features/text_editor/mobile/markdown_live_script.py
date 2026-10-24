"""WebView adapter for the shared live Markdown syntax rules."""

LIVE_SCRIPT = r'''
const livePatterns = LIVE_PATTERNS;
const inlinePatterns = livePatterns.inline.map(pattern => new RegExp(pattern, 'gu'));
const headingPattern = new RegExp(livePatterns.heading);
const originalText = new WeakMap();
for (const section of root.children) {
    const walker = document.createTreeWalker(section, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) originalText.set(walker.currentNode, walker.currentNode.data);
}
function textOffset(section, node, offset) {
    const range = document.createRange(); range.selectNodeContents(section);
    range.setEnd(node, offset); return range.toString().length;
}
function textPosition(section, offset) {
    const walker = document.createTreeWalker(section, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
        if (offset <= walker.currentNode.length) return [walker.currentNode, offset];
        offset -= walker.currentNode.length;
    }
    return [section, section.childNodes.length];
}
function liveSpans(text) {
    const spans = [], code = [];
    for (const pattern of inlinePatterns) {
        pattern.lastIndex = 0;
        for (const match of text.matchAll(pattern)) {
            const start = match.index, end = start + match[0].length;
            if (code.some(([first, last]) => first <= start && start < last)) continue;
            const marker = match.groups.marker;
            if (!marker.startsWith('`') && (text.slice(0, start).match(/(?<![\\`])`(?!`)/g) || []).length % 2) continue;
            spans.push({start, end, marker});
            if (marker.startsWith('`')) code.push([start, end]);
        }
    }
    return spans;
}
function renderTypedMarkup() {
    const selection = getSelection();
    if (!selection.rangeCount || !editableRange(selection.getRangeAt(0))) return;
    const range = selection.getRangeAt(0);
    const element = range.startContainer.nodeType === Node.TEXT_NODE ? range.startContainer.parentElement : range.startContainer;
    const section = element.closest('section');
    let first = textOffset(section, range.startContainer, range.startOffset);
    let last = textOffset(section, range.endContainer, range.endOffset);
    // Preserve source offsets while rebuilding display spans. WebView undo
    // cannot track these decorations; the bounded section history below owns it.
    for (const decoration of section.querySelectorAll('[data-live-decoration]')) {
        decoration.removeAttribute('data-live-decoration');
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
        if (originalText.get(node) === node.data) continue;
        const original = originalText.get(node);
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
        const block = node.parentElement.closest('p,div,li,h1,h2,h3,h4,h5,h6');
        const heading = block && block.firstChild === node && headingPattern.exec(text);
        if (heading && !/^H[1-6]$/.test(block.nodeName)) block.dataset.liveHeading = heading[1].length;
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
            if (marker) char.classList.add('live-marker');
            live.append(char);
        }
        node.replaceWith(live);
    }
    for (const block of section.querySelectorAll('[data-live-heading]')) {
        if (!headingPattern.test(block.textContent)) delete block.dataset.liveHeading;
    }
    const restored = document.createRange();
    restored.setStart(...textPosition(section, first)); restored.setEnd(...textPosition(section, last));
    selection.removeAllRanges(); selection.addRange(restored); savedRange = restored.cloneRange();
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
const undoEdits = [], redoEdits = [];
const sectionStates = new Map([...root.children].map(section => [section, {html:section.innerHTML, first:0, last:0}]));
let historyBytes = 0;
function captureState(section) {
    const selection = getSelection(), range = selection.rangeCount && selection.getRangeAt(0);
    return {html:section.innerHTML,
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
    savedRange = range.cloneRange(); publish(); scheduleCaretReveal();
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
