# Using documentation

Open Settings and scroll to Mobile documentation near the bottom. These guides
are bundled with the app and can be read offline.

## Browse folders and pages

In a narrow window, the hamburger button (☰) opens the documentation hierarchy
and search. Tap a page to read it, or tap the hamburger again to return to your
current page. The query and expanded folders stay in place.

When there is enough usable width, the tree stays on the left and the document
on the right. Resizing or rotating adapts the layout without reopening your page.
This works from the app's allocated space, including iPad windows, Android tablet
split-screen and full or partial foldable windows. Screen pixel count alone does
not determine the layout.

The + and − buttons expand or collapse a folder. Each child level is indented
further, with page titles aligned to folder titles at the same depth. Tap the folder's title to open its
own page, when it has one. For example, a documents folder containing documents.md
uses that file as its folder page, without repeating it as a child.

A heading at the start of the document body supplies the displayed title. It may
follow YAML properties enclosed in `---` delimiters and separating blank lines.
Otherwise, the filename or folder name supplies it. A heading below introductory
body text does not rename the navigation entry.

## Back, Forward and Up

The top bar keeps Back (‹), Forward (›) and Up (↑) visible in both browse and read
views. These icon buttons have accessible action labels.
Back and Forward revisit opened pages. Opening a new page after going Back starts
a new history branch. Up opens the containing folder's same-named page; if you
are already reading that folder page, it opens the parent folder's page. At the
guide root, README.md or index.md can serve as the folder page. Buttons are disabled
when there is no destination. Browsing and search state stay in place.

## Search in the window

Type in Search documentation, then choose File names & titles or Page text. Search
is case-insensitive. Matching pages keep their parent folders visible, so you can
see where they belong. Clear the query to restore the full hierarchy.

Page text searches the Markdown source across these guides. It lists matching
pages; it does not highlight every occurrence in the rendered article. Tap a result
to read the page. Relative Markdown page links also open within the guide.

## Relative links and text files

Links such as `../documents/remote.md` resolve from the page you are reading.
You can omit `.md`, or link to a folder that has a same-named page, README or index.
A link into a feature wiki opens that guide and changes the tree to that feature's scope. Back and Forward restore the corresponding scope as well.

Links to local text and code files such as `.txt` and `.py` open a separate text
editor session. They leave the documentation page and its history in place, and
are never run as programs. Return through Settings to resume the guide. A missing
or non-text file shows an explanation.

Both `[test.md|Test]` (alias form) and `[Test](test.md)` (standard Markdown) show
Test and open test.md. The double-bracket `[[test.md|Test]]` form also works.
Alias-like text inside inline code or fenced code stays literal.

## Reading formatted pages

Tables show header cells and borders; swipe a wide table sideways to read its
remaining columns. Headings, nested lists, quotes, bold, italics, strikethrough,
separators and code blocks render offline. Local inline and reference links open
pages; heading links such as `#reading-formatted-pages` jump within an article.
External links remain inert, images show their alternative text, and raw HTML
is displayed as text. Scripts and remote resources are blocked.
