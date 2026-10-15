"""Chapter-level labels shared by mobile library and provider readers.

These labels describe spine items; nested TOC fragments remain a separate
navigation capability, rather than being presented as supported destinations.
"""


def chapter_labels(book):
    titles = {}
    for chapter in book.chapters:
        titles.setdefault(chapter.path, chapter.label)
    return [f'{index + 1}. {titles.get(path, f"Chapter {index + 1}")}'
            for index, path in enumerate(book.spine)]
