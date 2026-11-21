"""Session-only published page visits for system Back, bounded to 100 steps."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"


class PageVisits:
    def __init__(self):
        self.current = None
        self.previous = []
        self.restoring = False

    def visit(self, position):
        if position == self.current:
            return
        if self.current is not None and not self.restoring:
            self.previous.append(self.current)
            del self.previous[:-100]
        self.current = position

    async def back(self, show):
        if not self.previous or self.restoring:
            return
        target = self.previous[-1]
        self.restoring = True
        try:
            await show(target)
            if self.current == target:
                self.previous.pop()
        finally:
            self.restoring = False
