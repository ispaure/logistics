"""Session-only published page visits for system Back, bounded to 100 steps."""


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
