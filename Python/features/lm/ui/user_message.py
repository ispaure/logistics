"""Literal user text with opt-in fenced code panels for the transcript."""
from markdown_it import MarkdownIt
from commonUtils.ui import pyside as qt


def set_user_document(document, source):
    """Keep prose literal; interpret only top-level explicit code fences.

    Work on a presentation copy. Stored source, clipboard message copies and
    server requests continue to use the original text.
    """
    text = source.replace('\r\n', '\n').replace('\r', '\n')
    document.setPlainText(text)
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line.encode('utf-16-le')) // 2)
    fences = [token for token in MarkdownIt('commonmark').parse(text)
              if token.type == 'fence' and token.level == 0]
    # Replace from the end so source line offsets remain valid.
    for token in reversed(fences):
        first, last = token.map
        start, end = offsets[first], offsets[last]
        if lines[last - 1].endswith('\n'):
            end -= 1
        cursor = qt.QTextCursor(document)
        cursor.setPosition(start)
        cursor.setPosition(end, qt.QTextCursor.MoveMode.KeepAnchor)
        code = token.content.removesuffix('\n')
        cursor.insertText(code)
        code_end = cursor.position()
        block = document.findBlock(start)
        while block.isValid() and block.position() <= code_end:
            fmt = qt.QTextBlockFormat()
            fmt.setNonBreakableLines(True)
            language = token.info.split()[0] if token.info.strip() else ''
            fmt.setProperty(qt.QTextFormat.Property.BlockCodeLanguage, language)
            qt.QTextCursor(block).setBlockFormat(fmt)
            block = block.next()
