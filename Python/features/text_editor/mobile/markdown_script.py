"""Offline editor DOM commands, block serialization and native change protocol."""

SCRIPT = r'''
const blocks = DATA;
const root = document.getElementById('document');
function tableBoundaries(section) {
    if (!section.querySelector('table')) return;
    const boundary = () => {
        const p = document.createElement('p'); p.dataset.editorBoundary = 'true'; p.innerHTML = '<br>'; return p;
    };
    if (section.firstElementChild?.nodeName === 'TABLE') section.prepend(boundary());
    if (section.lastElementChild?.nodeName === 'TABLE') section.append(boundary());
}
for (const [index, block] of blocks.entries()) {
    const section = document.createElement('section');
    section.dataset.index = index;
    section.innerHTML = block.html;
    tableBoundaries(section);
    section.contentEditable = block.editable ? 'true' : 'false';
    if (!block.editable && block.html) {
        section.title = 'Edit this block in Source mode';
        section.dataset.sourceOnly = 'true';
    }
    root.append(section);
    block.originalHTML = section.innerHTML;
}
function inline(node) {
    if (node.nodeType === Node.TEXT_NODE)
        return node.data.replace(/\\/g, '\\\\').replace(/([*_`\[\]<>])/g, '\\$1');
    if (node.dataset && node.dataset.markdown) return node.dataset.markdown;
    const text = Array.from(node.childNodes, inline).join('');
    switch (node.nodeName) {
    case 'STRONG': case 'B': return '**' + text + '**';
    case 'EM': case 'I': return '*' + text + '*';
    case 'S': case 'STRIKE': case 'DEL': return '~~' + text + '~~';
    case 'CODE': {
        const raw = node.textContent;
        const fence = '`'.repeat(Math.max(0, ...Array.from(raw.matchAll(/`+/g), m => m[0].length)) + 1);
        return fence + ' ' + raw + ' ' + fence;
    }
    case 'BR': return '\n';
    case 'A': {
        const href = (node.getAttribute('href') || '').replace(/\(/g, '%28').replace(/\)/g, '%29');
        const title = node.getAttribute('title');
        return '[' + text + '](' + href + (title ? ' "' + title.replace(/"/g, '\\"') + '"' : '') + ')';
    }
    case 'SPAN': {
        let styled = text;
        if (node.style.fontWeight === 'bold' || Number(node.style.fontWeight) >= 600) styled = '**' + styled + '**';
        if (node.style.fontStyle === 'italic') styled = '*' + styled + '*';
        if (node.style.textDecoration.includes('line-through')) styled = '~~' + styled + '~~';
        return styled;
    }
    case 'DIV': return '\n' + text;
    // Native editing engines can introduce extra wrappers. Retain their text
    // even when their visual style has no Markdown equivalent.
    default: return text;
    }
}
function serialize(node) {
    if (node.nodeType === Node.TEXT_NODE) return inline(node);
    const children = () => Array.from(node.childNodes, serialize).join('');
    switch (node.nodeName) {
    case 'SECTION': {
        let result = '', run = '';
        const flush = () => {if (run.trim()) result += run.trim() + '\n\n'; run = '';};
        for (const child of node.childNodes) {
            if (/^(P|DIV|H[1-6]|UL|OL|PRE|BLOCKQUOTE|TABLE)$/.test(child.nodeName)) {
                flush(); result += serialize(child);
            } else if (child.nodeType !== Node.TEXT_NODE || child.data.trim()) run += inline(child);
        }
        flush();
        return result;
    }
    case 'DIV':
        if (node.className === 'table-scroll') return children();
        return Array.from(node.childNodes, inline).join('').trimEnd() + '\n\n';
    case 'P':
        if (node.dataset.editorBoundary && !node.textContent) return '';
        return Array.from(node.childNodes, inline).join('').trimEnd() + '\n\n';
    case 'H1': case 'H2': case 'H3': case 'H4': case 'H5': case 'H6':
        return '#'.repeat(Number(node.nodeName[1])) + ' ' + Array.from(node.childNodes, inline).join('') + '\n\n';
    case 'BLOCKQUOTE': return children().trimEnd().split('\n').map(s => '> ' + s).join('\n') + '\n\n';
    case 'TABLE': {
        const rows = Array.from(node.rows, row => Array.from(row.cells, cell =>
            Array.from(cell.childNodes, inline).join('').replace(/\|/g, '\\|').replace(/\n/g, '<br>')));
        if (!rows.length) return '';
        return '| ' + rows[0].join(' | ') + ' |\n| ' + rows[0].map(() => '---').join(' | ') + ' |\n'
            + rows.slice(1).map(row => '| ' + row.join(' | ') + ' |').join('\n') + '\n\n';
    }
    case 'UL': case 'OL': {
        const start = Number(node.getAttribute('start') || 1);
        return Array.from(node.children, (li, i) => {
            const value = Array.from(li.childNodes, child =>
                ['UL','OL'].includes(child.nodeName) ? '\n' + serialize(child) :
                ['P','DIV'].includes(child.nodeName) ? serialize(child) : inline(child)).join('').trimEnd();
            const marker = node.nodeName === 'OL' ? (start+i)+'. ' : '- ';
            return marker + value.split('\n').join('\n' + ' '.repeat(marker.length));
        }).join('\n') + '\n\n';
    }
    case 'PRE': {
        const raw = node.textContent.replace(/\n$/, '');
        const fence = '`'.repeat(Math.max(2, ...Array.from(raw.matchAll(/`+/g), m => m[0].length)) + 1);
        const code = node.querySelector('code');
        const language = code && (code.className.match(/language-([\w+-]+)/) || [,''])[1] || '';
        return fence + language + '\n' + raw + '\n' + fence + '\n\n';
    }
    default: return inline(node);
    }
}
let revision = 0;
const byteSizes = blocks.map(block => new TextEncoder().encode(block.source).length);
let totalBytes = byteSizes.reduce((sum, size) => sum + size, 0);
const changes = new Map();
function publish(notify=true) {
    try {
        let previousEnding = '';
        for (const section of root.children) {
            const index = Number(section.dataset.index), block = blocks[index];
            const html = section.innerHTML;
            if (html !== (block.publishedHTML ?? block.originalHTML)) {
                if (html === block.originalHTML) changes.delete(index);
                else {
                    const edited = serialize(section).replace(/\n+$/, '');
                    const ending = block.source.match(/\n*$/)[0];
                    const prefix = block.source === '' && previousEnding ?
                        (previousEnding.endsWith('\n\n') ? '' : previousEnding.endsWith('\n') ? '\n' : '\n\n') : '';
                    changes.set(index, prefix + edited + (ending || '\n\n'));
                }
                const source = changes.has(index) ? changes.get(index) : block.source;
                totalBytes -= byteSizes[index];
                byteSizes[index] = new TextEncoder().encode(source).length;
                totalBytes += byteSizes[index];
                block.publishedHTML = html;
            }
            const source = changes.has(index) ? changes.get(index) : block.source;
            if (source) previousEnding = source.slice(-2);
        }
        if (totalBytes > 1024 * 1024) throw Error('Formatted editing is limited to 1 MiB.');
        // Cumulative changed blocks tolerate a WebView coalescing navigation events.
        // Untouched source never crosses the bridge again; no document is persisted.
        const patch = {revision: ++revision, changes: Array.from(changes)};
        if (notify) location.href = BRIDGE + '?patch=' + encodeURIComponent(JSON.stringify(patch));
        document.getElementById('notice').textContent = '';
        return patch;
    } catch (error) {
        document.getElementById('notice').textContent = error.message + ' Undo this change before switching modes.';
    }
}
// Native Save obtains the current DOM even if WebKit coalesced a navigation
// notification, or composition has not yet sent its final input event.
window.markdownSnapshot = () => publish(false);
document.documentElement.dataset.editorReady = 'true';
// The document is the only writing scroller. Reveal the caret only when it
// actually leaves that viewport; never recenter it after every keystroke.
let caretFrame = null;
function revealCaret() {
    caretFrame = null;
    const selection = getSelection();
    if (!root.contains(document.activeElement) || !selection.rangeCount || !selection.isCollapsed) return;
    const range = selection.getRangeAt(0).cloneRange();
    if (!editableRange(range)) return;
    let rect = range.getBoundingClientRect();
    if (!rect.height && range.startContainer.nodeType === Node.TEXT_NODE && range.startOffset > 0) {
        range.setStart(range.startContainer, range.startOffset - 1);
        rect = range.getBoundingClientRect();
    }
    if (!rect.height) return;
    const bounds = root.getBoundingClientRect();
    const viewport = window.visualViewport;
    const visibleTop = Math.max(bounds.top, viewport ? viewport.offsetTop : 0);
    const visibleBottom = Math.min(bounds.bottom, viewport ? viewport.offsetTop + viewport.height : innerHeight);
    // A phone keyboard and large fonts can leave barely one visible line.
    // Fixed padding then makes fitting the caret impossible and scrolls it
    // above the writing area on successive input/composition events.
    const padding = Math.max(0, Math.min(12, (visibleBottom - visibleTop - rect.height) / 2));
    const top = visibleTop + padding, bottom = visibleBottom - padding;
    if (bottom <= top) return;
    if (rect.bottom > bottom) root.scrollTop += rect.bottom - bottom;
    else if (rect.top < top) root.scrollTop += rect.top - top;
}
function scheduleCaretReveal() {
    if (caretFrame === null) caretFrame = requestAnimationFrame(revealCaret);
}
root.addEventListener('input', event => {
    if (!event.isComposing) { publish(); scheduleCaretReveal(); }
});
root.addEventListener('compositionend', () => { publish(); scheduleCaretReveal(); });
root.addEventListener('focusout', () => publish());
root.addEventListener('focusin', scheduleCaretReveal);
root.addEventListener('keyup', event => {
    if (/^(Arrow|Home|End|Page)/.test(event.key)) scheduleCaretReveal();
});
window.addEventListener('resize', scheduleCaretReveal);
window.visualViewport?.addEventListener('resize', scheduleCaretReveal);
root.addEventListener('paste', event => {
    event.preventDefault();
    document.execCommand('insertText', false, event.clipboardData.getData('text/plain'));
});
let savedRange = null;
function editableRange(range) {
    const element = node => node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
    const first = element(range.startContainer)?.closest('section[contenteditable=true]');
    const last = element(range.endContainer)?.closest('section[contenteditable=true]');
    return first && first === last && root.contains(first);
}
document.addEventListener('selectionchange', () => {
    const selection = getSelection();
    if (root.contains(document.activeElement) && selection.rangeCount && editableRange(selection.getRangeAt(0))) savedRange = selection.getRangeAt(0).cloneRange();
    for (const button of document.querySelectorAll('[data-command]')) {
        if (['bold', 'italic', 'strikeThrough', 'insertUnorderedList', 'insertOrderedList'].includes(button.dataset.command))
            button.setAttribute('aria-pressed', String(document.queryCommandState(button.dataset.command)));
    }
});
function restoreRange(rangeOverride=null) {
    const selection = getSelection();
    if (rangeOverride && editableRange(rangeOverride)) savedRange = rangeOverride.cloneRange();
    else if (root.contains(document.activeElement) && selection.rangeCount && editableRange(selection.getRangeAt(0)))
        savedRange = selection.getRangeAt(0).cloneRange();
    if (!savedRange || !editableRange(savedRange)) {
        savedRange = document.createRange();
        savedRange.selectNodeContents(root.querySelector('section[contenteditable=true]'));
        savedRange.collapse(false);
    }
    const range = savedRange.cloneRange();
    const container = range.commonAncestorContainer;
    const element = container.nodeType === Node.ELEMENT_NODE ? container : container.parentElement;
    element.closest('section[contenteditable=true]').focus({preventScroll:true});
    selection.removeAllRanges();
    selection.addRange(range);
    savedRange = range.cloneRange();
    return selection;
}
document.querySelector('nav').addEventListener('pointerdown', () => {
    const selection = getSelection();
    if (root.contains(document.activeElement) && selection.rangeCount && editableRange(selection.getRangeAt(0))) savedRange = selection.getRangeAt(0).cloneRange();
}, true);
document.querySelector('nav').addEventListener('click', event => {
    if (event.target.closest('button')) {
        document.querySelector('nav details').open = false;
        scheduleCaretReveal();
    }
});
document.addEventListener('pointerdown', event => {
    if (!event.target.closest('nav')) document.querySelector('nav details').open = false;
});
document.addEventListener('keydown', event => {
    if (event.key === 'Escape') document.querySelector('nav details').open = false;
});
function command(name, value=null) {
    restoreRange();
    document.execCommand(name, false, value);
    publish();
}
document.querySelectorAll('[data-command]').forEach(button => {
    button.addEventListener('mousedown', event => event.preventDefault());
    button.addEventListener('click', () => command(button.dataset.command, button.dataset.value || null));
});
document.getElementById('block-style').addEventListener('change', event => {
    command('formatBlock', event.target.value);
    event.target.value = '';
});
document.getElementById('inline-code').addEventListener('click', () => {
    const selection = restoreRange();
    const code = document.createElement('code');
    code.textContent = selection.toString() || 'code';
    command('insertHTML', code.outerHTML);
});
const linkDialog = document.getElementById('link-dialog');
const linkTarget = document.getElementById('link-target');
const linkError = document.getElementById('link-error');
let linkRange = null;
document.getElementById('show-link').addEventListener('click', () => {
    const selection = restoreRange();
    linkRange = selection.getRangeAt(0).cloneRange();
    const node = selection.anchorNode;
    const element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
    linkTarget.value = element.closest('a')?.getAttribute('href') || '';
    linkError.textContent = '';
    linkDialog.showModal();
    linkTarget.focus();
    linkTarget.select();
});
function cancelLink() {
    linkDialog.close();
    restoreRange(linkRange);
}
document.getElementById('cancel-link').addEventListener('click', cancelLink);
linkDialog.addEventListener('cancel', event => { event.preventDefault(); cancelLink(); });
function applyLink() {
    const href = document.getElementById('link-target').value.trim().replace(/ /g, '%20');
    if (!href || /[\x00-\x20<>]/.test(href) || href.startsWith('//') ||
        (/^[\w+.-]+:/.test(href) && !/^(https?:|mailto:)/i.test(href))) {
        linkError.textContent = 'Enter a relative file path, https:// address or mailto: link.';
        linkTarget.focus();
        return;
    }
    linkDialog.close();
    const selection = restoreRange(linkRange);
    if (selection.isCollapsed) {
        const anchor = document.createElement('a');
        anchor.setAttribute('href', href);
        anchor.textContent = 'Link';
        command('insertHTML', anchor.outerHTML);
    } else command('createLink', href);
}
document.getElementById('apply-link').addEventListener('click', applyLink);
linkTarget.addEventListener('keydown', event => {
    if (event.key === 'Enter') { event.preventDefault(); applyLink(); }
});
function tableCommand(action) {
    const selection = restoreRange();
    if (action === 'insert') {
        command('insertHTML', '<table><thead><tr><th>Header</th><th>Header</th></tr></thead><tbody><tr><td>Cell</td><td>Cell</td></tr></tbody></table><p><br></p>');
        return;
    }
    const node = selection.anchorNode;
    const element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
    const cell = element.closest('td,th'), table = element.closest('table');
    if (!table || !cell) {
        document.getElementById('notice').textContent = 'Place the cursor in a table cell first.';
        return;
    }
    const clone = table.cloneNode(true), row = cell.parentElement.rowIndex, column = cell.cellIndex;
    if (action === 'row') {
        const added = clone.insertRow(row+1);
        for (let index=0; index<table.rows[row].cells.length; index++) added.insertCell().textContent = 'Cell';
    } else if (action === 'column') {
        for (const existing of clone.rows) {
            const added = document.createElement(existing.rowIndex === 0 ? 'th' : 'td');
            added.textContent = existing.rowIndex === 0 ? 'Header' : 'Cell';
            existing.insertBefore(added, existing.cells[column+1] || null);
        }
    } else if (action === 'delete-row') clone.deleteRow(row);
    else if (action === 'delete-column') for (const existing of clone.rows) existing.deleteCell(column);
    // WebKit canonicalizes a bare table selection into its first cell. Replace
    // the enclosing editing block between real paragraph caret positions.
    const section = table.closest('section');
    tableBoundaries(section);
    const replacement = section.cloneNode(true);
    const index = Array.from(section.querySelectorAll('table')).indexOf(table);
    const result = clone.rows.length && clone.rows[0].cells.length ? clone : document.createElement('p');
    if (!result.hasChildNodes()) result.innerHTML = '<br>';
    replacement.querySelectorAll('table')[index].replaceWith(result);
    const range = document.createRange();
    range.selectNodeContents(section);
    selection.removeAllRanges(); selection.addRange(range);
    savedRange = range.cloneRange();
    // A single native replacement keeps structural table edits undoable.
    document.execCommand('insertHTML', false, replacement.innerHTML);
    publish();
}
document.querySelectorAll('[data-table]').forEach(button => {
    button.addEventListener('mousedown', event => event.preventDefault());
    button.addEventListener('click', () => tableCommand(button.dataset.table));
});
'''
