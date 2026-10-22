"""Prepare before retiring pixels; reject work belonging to a retired reader."""
from .sources import capture_library, capture_provider


class ReadingPublication:
    def __init__(self, owner, container, current):
        self.owner, self.container, self.current = owner, container, current
        self.begun = False

    @classmethod
    def library(cls, owner):
        return cls(owner, owner.book_content, capture_library(owner))

    @classmethod
    def provider(cls, owner, view):
        return cls(owner, view.crypt_content, capture_provider(owner, view))

    def begin(self, direction):
        if not self.current():
            return False
        from mobile.page_animation import begin_page_slide
        begin_page_slide(self.container, direction, self.owner.preferences.values)
        self.begun = True
        return True

    def mount(self, surface, *, direction=0, publish=None, keep=(), retired=()):
        if not self.current():
            if surface not in self.container.children and surface not in keep and hasattr(surface, 'dispose'):
                surface.dispose()
            return False
        from mobile.page_animation import finish_page_slide
        if not self.begun:
            self.begin(direction)
        if publish is not None:
            publish()
        disposed = set()
        for child in [*self.container.children, *retired]:
            if child is not surface and child not in keep and id(child) not in disposed:
                if hasattr(child, 'dispose'):
                    child.dispose()
                disposed.add(id(child))
        for child in list(self.container.children):
            self.container.remove(child)
        self.container.add(surface)
        finish_page_slide(self.container, direction, self.owner.preferences.values)
        return True

    def footer(self, view, *, comic, count, index, right_to_left=False, chapter=None):
        if not self.current():
            return False
        footer = getattr(view, 'page_footer', None)
        if footer is not None:
            footer.sync(comic=comic, count=count, index=index, right_to_left=right_to_left)
            if chapter is not None:
                footer.chapter_progress(index, count, *chapter)
        self.chrome()
        return True

    def chrome(self):
        if not self.current():
            return False
        from mobile.reader_chrome import sync_comic_chrome
        app = getattr(self.owner, 'app', self.owner)
        sync_comic_chrome(app, app.body)
        from mobile.external_display import sync
        sync(app)
        return True
