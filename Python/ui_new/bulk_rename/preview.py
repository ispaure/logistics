"""Paint filename changes as plain text with changed spans in bold."""
from difflib import SequenceMatcher
from commonUtils.ui import pyside as qt


def changed_spans(original, proposed):
    return tuple((start, end) for kind, _, _, start, end in
                 SequenceMatcher(None, original, proposed, autojunk=False).get_opcodes()
                 if kind in ('insert', 'replace') and start != end)


def preview_tooltip(original, proposed):
    removed = [original[start:end] for kind, start, end, _, _ in
               SequenceMatcher(None, original, proposed, autojunk=False).get_opcodes()
               if kind == 'delete']
    return proposed + ('\nRemoved: ' + ' · '.join(removed) if removed else '')


def change_formats(original, proposed):
    formats = []
    for start, end in changed_spans(original, proposed):
        span = qt.QTextLayout.FormatRange()
        # QTextLayout positions count UTF-16 units, including emoji surrogate pairs.
        span.start = len(proposed[:start].encode('utf-16-le')) // 2
        span.length = len(proposed[start:end].encode('utf-16-le')) // 2
        span.format.setFontWeight(qt.QFont.Weight.Bold)
        formats.append(span)
    return formats


class RenamePreviewDelegate(qt.QStyledItemDelegate):
    def paint(self, painter, option, index):
        styled = qt.QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        text = styled.text
        styled.text = ''
        style = styled.widget.style() if styled.widget else qt.QApplication.style()
        style.drawControl(qt.QStyle.ControlElement.CE_ItemViewItem, styled, painter, styled.widget)
        rect = style.subElementRect(qt.QStyle.SubElement.SE_ItemViewItemText, styled, styled.widget)
        layout = qt.QTextLayout(text, styled.font)
        layout.setFormats(change_formats(index.siblingAtColumn(0).data(), text))
        settings = qt.QTextOption()
        settings.setWrapMode(qt.QTextOption.WrapMode.NoWrap)
        layout.setTextOption(settings)
        layout.beginLayout()
        line = layout.createLine()
        if line.isValid(): line.setLineWidth(rect.width())
        layout.endLayout()
        painter.save()
        painter.setClipRect(rect)
        selected = bool(styled.state & qt.QStyle.StateFlag.State_Selected)
        painter.setPen(styled.palette.color(qt.QPalette.ColorRole.HighlightedText if selected
                                            else qt.QPalette.ColorRole.Text))
        layout.draw(painter, qt.QPointF(rect.left(), rect.top() + (rect.height()-layout.boundingRect().height())/2))
        painter.restore()
