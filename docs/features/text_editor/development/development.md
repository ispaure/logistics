# Text Editor

For workflows, settings and troubleshooting, see the [user guide](../user/user.md).

The [Mobile Markdown editor and library rework](mobile-markdown-rework.md) records
the redesign, storage permissions, refactoring and remaining native acceptance gates.

An optional Logistics feature for plain text and code, independent of Books,
Comics and the shared Markdown reader. Open **Settings → Text Editor → Open Text
Editor**, or use **Open in Text Editor** in a browser. Each file has one editor
pane in the application's document workspace, and can detach into its own window.
Reopening a file focuses its existing pane. Disabling the feature removes
contributions while retaining open documents for re-enablement.

## Architecture

| Module | Responsibility |
| --- | --- |
| `contributions.py`, `ui/page.py` | Lazy feature registration, entry point and browser integration |
| `mobile/provider_markdown.py` | Provider Markdown modes, web surfaces, preview tasks, search/speech attachment and cleanup; test with `mobile_build/tests/editing/test_provider_markdown.py` and `test_markdown_editor.py` |
| `ui/service.py` | Per-document window ownership and browser save notifications |
| `ui/window.py` | Single-document presentation, menus, status and close lifecycle |
| `ui/document.py` | Per-document snapshot, encoding and editing metadata |
| `ui/file_operations.py` | Queued background loads/saves, conflicts and disk notifications |
| `ui/editing.py` | Application commands, nonmodal search integration and status controls |
| `ui/session.py`, `ui/commands.py` | Private recovery checkpoints, safe session restore, command discovery and shortcuts |
| `ui/syntax_settings.py`, `preferences.py` | Desktop language chooser, syntax application and existing INI-based preferences |

The shared dock workspace owns document tabs, splitting and detachment. Editors
have no nested tab bar. File → New opens another document pane; opening a file
reuses an untouched blank document or opens another pane without an extra Untitled
buffer. Each pane retains its existing `OperationProgress` worker and
`RecentFiles` implementation.

Reusable Qt-independent file IO lives in `commonUtils.persistence.text`. The shared
`commonUtils.ui.code_editor` package supplies the gutter, code editing, search
and syntax components; it imports no Logistics modules. Existing public text,
INI, Markdown, EPUB and comic APIs retain their behavior. No file-type registry
rules are replaced. Conditional generic activation preserves specialized
non-text file handling and the built-in Markdown reader; explicit text-editor
opening remains available for Markdown and other text formats.

`EditingCommands._build_editing` builds named search, line/selection,
structure/compare/tools and preference command groups in their existing order.
It retains Escape, hidden preference-shortcut reconciliation and status controls.
Group callbacks keep their captured loop values and route through the same editor
commands. Search lifetime, Save/Save As, undo, source bytes and document ownership
remain with their existing components.

## Shared language selection

Both editor presentations use commonUtils' toolkit-independent
`formats.code_language.LanguageSelection` and `runtime.choices.ChoiceSet`.
The [shared language API](../../../../Python/commonUtils/docs/reference/formats/formats.md#editor-language-selection)
owns IDs, catalogue expansion and automatic/manual detection mechanics. Desktop
`Document` retains its model; mobile binds directly to CodeInput's model rather
than keeping a second override. Logistics retains the chooser/dropdown, the
“Automatic · language” status caption, per-document ownership and applying desktop
syntax to highlighting, both split views' folding and comments.

Desktop recovery stores optional `language_override` alongside the existing
`language` field. New checkpoints preserve Automatic versus manual choices;
older checkpoints retain their recorded effective language as a manual choice.
Mobile selection stays with the retained editor view and is not added to the
workspace manifest. Desktop chooser/save/recovery and mobile dropdown/rename tests
cover these adapters; shared model/choice/CodeInput tests live in commonUtils.
Host checks use offscreen Qt and Toga's dummy backend, not physical devices.

The native document acceptance checks retain pre-existing persistent workspace
identities, including open notebooks, while verifying restoration of both text
drafts. The disposable `document_storage_tools` runner's `--probe documents`
executes notebook acceptance followed by these document checks on iOS or Android;
it also covers native Back, preferences, close decisions and Markdown ownership.
The runner removes its QA app and owned device after collecting results.

## Notes document ownership

The desktop Notes library clears `viewer.document_state` when retiring a private
draft, then clears the reading/source/formatted surfaces. Saved byte and rich
baselines therefore retire through the declared shared owner rather than through
separate private viewer attributes. The ownership contract is documented in
[commonUtils Markdown](../../../../Python/commonUtils/docs/reference/ui/markdown/markdown.md#internal-ownership-and-embedding-contracts),
and `test_notes_library_desktop.py` verifies that retired drafts retain no saved
byte baseline.

## Highlighting dependency

Logistics pins pure-Python **Pygments 2.19.2** in its project and lockfile. Its
maintained language definitions support the requested languages and additional
manual choices without Qt ABI or platform binaries. It uses BSD-2-Clause licensing;
the shared adapter includes attribution in `PYGMENTS_LICENSE.txt`.
See [Pygments architecture](https://pygments.org/docs/quickstart/) and
[project source/license](https://github.com/pygments/pygments).

The incremental Qt adapter carries RegexLexer state between text blocks and
rehighlights affected blocks. The compiled-rule adapter is version-specific and
covered by the pinned-version tests. Extended/delegating lexers (including YAML
and JSON) use per-block fallback; their complex multiline constructs may have
less complete highlighting. Highlighting never parses or executes application
code. Unsupported definitions fall back to plain text.

## File safety and limits

`FileOperations.save_document()` owns destination selection, choice release and
private handoff policy. `_confirm_save_overwrite()` returns the confirmed file
revision or `None` after cancellation/error. `_save_local_document()` captures the
snapshot, text and encoding options before queuing the existing local write; its
completion/failure callbacks restore the captured read-only state. These helpers
remain in `ui/file_operations.py`. The private handoff still defers its recovery
gate to publication and retires the original draft only after successful transfer.

- Reads and encoded writes run in owned workers; widget updates remain on Qt's GUI thread.
- Strict UTF decoding recognizes BOMs. Legacy encodings require explicit selection;
  byte replacement is never automatic. Forced binary opening is explicit.
- No-op saves preserve bytes, including BOMs, mixed endings and final newlines.
  Changed lines use the file's detected dominant ending; aligned unchanged mixed
  lines retain their own endings. Unicode paragraph separators survive Qt normalization.
- Encoding/line-ending conversions happen only after an explicit user choice.
- Atomic sibling staging, fsync, original permissions and conflict rechecks protect
  saves. A deleted original requires Save As. Symlinks resolve to their targets;
  canonical paths prevent duplicate tabs for the same resolved path.
- New destinations use no-clobber creation. As with other atomic rename workflows,
  an arbitrary external process can still race the final filesystem promotion.
- Files above 1 MiB use simpler presentation; files above 16 MiB are refused.
  Blocks above 20,000 characters skip syntax formatting. Search stops at 50,000
  matches and disables Replace All when truncated; occurrence highlighting caps
  at 1,000 matches and is omitted for large files. Regex patterns have PCRE resource limits.
- Private session checkpoints run in a serialized background executor, with atomic
  replacement and fsync. Per-session QLockFile ownership prevents concurrent-instance
  overwrite/restoration. Closing the last editor releases its recovery writer and
  lock; late document callbacks cannot restart them until another editor opens.
  Original bytes remain the save-conflict baseline for dirty restored files; clean
  files reload current disk content.
- Individual document closure prompts for modified buffers. Application shutdown or
  explicit session suspension waits for the latest durable checkpoint and retains
  buffers without saving originals. Recovery failure falls back to normal prompts.
- Recovery restores editor buffers, two-view orientation, cursors/selections and scroll
  positions on the next editor opening. It does not reproduce the outer workspace's
  dock layout or detached-window placement. Limits: 100 documents / 64 MiB checkpoint;
  edits after the last completed checkpoint can be lost in a crash.
- Diff uses owned background loading/comparison and a reusable side-by-side/unified
  dialog. Applying one change validates the captured buffer and forms one undo block.
  Comparison is capped at 1 MiB / 5,000 lines per side.
- Structural folding is shared across views and bounded to 256 KiB / 10,000 lines.
  Text transformations, multi-cursor commands, format/validation and EditorViews
  remain reusable commonUtils components. XML formatting refuses semantic-risk
  constructs; JSON formatting preserves original number/key tokens.

## Validation

From the checkout root:

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=Python .venv/bin/python -m unittest discover -s Python/tests -p test_text_editor.py -v
QT_QPA_PLATFORM=offscreen PYTHONPATH=Python .venv/bin/python -m unittest discover -s Python/commonUtils/tests -p 'test_code*.py' -v
PYTHONPATH=Python .venv/bin/python -m unittest discover -s Python/commonUtils/tests -p test_text_files.py -v
```

Tests cover byte preservation, legacy and Unicode encodings, conflicts, binary
handling, queue/window lifetime, shared browser activation, feature toggles,
search/replace undo, language definitions and theme-safe presentation. Headless Qt regressions run on macOS, Windows, Ubuntu and Fedora in CI.
Native desktop interaction, including platform window behavior, requires separate
manual validation.


## Additional regression checks

Run `test_text_editor*.py` for feature lifecycle, commands, diff, split views and
recovery failure paths. The reusable `test_code*.py`, `test_session_store.py`,
`test_text_files.py` and `test_workspace.py` suites cover the shared components.
`test_document_workspace.py`, `test_main_window.py` and
`test_application_instance.py` cover surrounding Logistics integration. These
headless Qt checks run on macOS, Windows, Ubuntu, and Fedora 43 in CI; native
desktop interaction still benefits from manual validation. New UI surfaces have also been rendered and inspected in both themes.

## Merge external changes

**Compare → Merge Disk Changes…** (also **Merge…** in the external-change banner)
compares the last loaded/saved snapshot with the editor buffer and current disk
file. The shared three-pane merge widget offers independent changes, per-hunk
choices and manual result edits with undo/redo. Applying checks that both the
buffer and disk snapshot are still current, replaces the buffer in one undo block,
and updates its disk baseline. Save remains explicit; Cancel changes neither.
Comparisons now refresh after each accepted hunk and use resizable, linked panes.

## Mobile editor

`mobile/provider_markdown.py` owns one `ProviderMarkdown` workflow per provider-backed
Markdown document. Its `source` is the session's existing code input: formatted
edits update that same input, without a second draft or persistence owner.
The controller owns preview/formatted surfaces, mode, render token/task, search,
speech attachment and Markdown controls. Suspend clears transient surfaces while
retaining the mode and draft; close disposes them permanently. Render results and
errors must still match the source, reader, access stamp and live document before
publication. Cancellation alone does not make a worker result current.

`ProviderMarkdownHost` enumerates rendering, image resources, font/appearance,
validity, busy state, speech, menu and toolbar callbacks. Composition lives in
`mobile.composition.presentation.provider_markdown`; the feature never imports the
application host. `ProviderUI` retains forwarding methods and state aliases for
existing callers, plus non-Markdown controls. Private sessions keep document
identity, credentials, saving, Save As, conflicts, memory budgets and dirty-close
policy. Prepared replacement adopts the new workflow after retiring the previous
one, including when changing back to plain text.

Run `python3 dev.py test mobile test_provider_markdown.py` for ownership, stale
results/errors, lock/close and replacement regressions. Also run
`test_markdown_*.py`, `test_private_sessions.py` and `test_remote_readers.py`.
`Python/tests/test_mobile_packaging.py` checks allowlist omissions;
`mobile_build/tests/tooling/test_packaged_startup.py` opens a provider Markdown view and switches between preview and editing
using only freshly staged sources. See the root [validation guide](../../../development/testing.md)
for environment setup (`py` instead of `python3` on Windows).

`mobile/ui.py` owns native editor widgets and per-document callbacks.
`mobile/markdown_editor.py` supplies the offline formatted Markdown surface used
by managed and provider-backed documents. It preserves exact untouched block
source, sends edits through a per-load navigation token, and updates the existing
source buffer for persistence. Source remains available for unsupported syntax.
Formatted and Source are mutually exclusive; legacy split preferences are retired
on load. Complex syntax remains protected in formatted mode and editable in
Source; images render as inert alt text, and arbitrary navigation is rejected.
No-op mode switches preserve Markdown bytes through the existing text session.
`markdown_editor` persists the per-session editing surface, independently
of the reading/editing `markdown_mode`. Ordinary Markdown opening defaults to
preview, while New and explicit edit commands enter editing. Each managed
document owns its preview WebView too, so paired/resumed previews do not replace
another session’s content; closing a document retires both WebViews.
The formatted page uses a fixed-height flex column with one scrolling document
area and a stationary formatting toolbar. The HTML/body do not scroll separately.
Its trailing editable section fills the remaining writing area, so blank-page
taps reach a native `contenteditable` target. Keyboard/viewport resizing and
typing schedule a coalesced caret check; it scrolls only enough to reveal a caret
outside the document viewport, rather than recentering it on every keystroke.
The caret's desired 12-pixel vertical breathing room shrinks to the space left
around one line when a phone keyboard or enlarged text leaves a short viewport.
Otherwise fixed padding can scroll the caret above the document area even when
the native editor panel itself stays in place. The Android keyboard probe checks
native IME composition, caret bounds, ancestor scroll offsets, new documents and
appending to the last Markdown block at phone sizes.
Live bold, italic, inline-code and heading markers follow the caret/selection
intervals used by desktop, rather than focus on the enclosing section. Inline
markers reveal when the caret touches their span or a selection overlaps it;
heading markers reveal across that heading. The grammar, inline parser adapter
and interval contract live in `commonUtils.formats.markdown.editing`. Supported
single-line paragraph/headings retain source delimiters when loaded; complex
blocks retain their existing rich/source fallback. Native toolbar inline edits
materialize source delimiters too. Visibility changes use a separate stylesheet,
leaving editable HTML, source, dirty state and undo snapshots untouched.
Browser regressions in `Python/tests/test_mobile_markdown_editing_dom.py` compare
visibility against the desktop predicate, including UTF-16 positions, selections,
paragraph transitions, loaded source and toolbar undo/redo. These host browser
checks do not replace iOS WebKit or Android WebView device validation.

IME composition is published only after completion. Native source/plain-text
editing retains its platform caret behavior. Status and line-count captions are
updated only when their text changes to avoid relaying out the editor on each key.
The Format menu's link command opens a modal HTML dialog instead of keeping a URL
field in the toolbar. It snapshots the editable range before moving focus to the
URL input and restores that exact range on insertion or cancellation, including
when WebKit restores focus as the dialog closes. Unsafe URL schemes remain
rejected before applying an undoable native link command.
Memory-pressure cleanup retains the active provider Markdown surface, including
its reading/editing choice. Android can request trimming while the activity is
backgrounded; clearing that preview would expose the retained source input on
wake. Normal navigation still suspends hidden provider WebViews and reconstructs
the chosen surface on resume. Both mobile Markdown Web surfaces use Apple's
system font names followed by generic `sans-serif`, allowing Android's device
font choice instead of WebView's `system-ui` face; code remains monospace.
`resources.py` owns provider text adapters, and `names.py` owns display-name
validation. The mobile application supplies
`services.mobile_presentation.MobilePresentation`; managed recovery records,
picker workflows and scene ownership remain host concerns. Both platforms reuse
commonUtils text persistence and conflict handling.

Managed text/Markdown menus expose confirmed deletion in editing and preview.
The host rechecks session ownership and window count after confirmation, removes
Recent/import identities and both DocumentStore files, then closes and disposes
the editor without checkpointing it again. Failed removal retains the open
buffer; ordinary close/discard still preserves the stored document. Provider
files use their existing folder-owned deletion workflow.

Closing an iOS editor stops its live WebView and detaches WebKit delegates before
replacing preview content. Queued native navigation decisions must not outlive
the Toga interface. Native close/discard checks explicitly collect closed editors.
Regression coverage lives in `mobile_build/tests/editing/test_markdown_editor.py`,
`test_source_editor.py` and the workspace/provider suites. The isolated native
`editor_probe.py` checks blank-page hit targets, default preview, formatted typing and toolbar edits,
source fallback, table structure undo/redo and unchanged neighboring syntax in
iPhone/iPad WebKit. Table replacements use paragraph caret boundaries around
the enclosing editable block: WebKit otherwise inserts a replacement table
inside its first cell. Replacing the block stays in the native undo history.

The custom source input also disables available iOS scroll-edge overlays because
it bypasses ordinary Toga text-input creation and its host appearance hook.

## Desktop presentation

Desktop widgets and controllers live in feature-owned `ui/`. Registration stays lazy; portable domain modules do not import this package. IDE/Text Editor change-marker and hunk integration is shared through `services/editors/ui/`.

## Mobile source manifest

`../../mobile_sources.json` declares this feature's selected portable/mobile sources. Update it when adding an imported module. The build tool aggregates and checks the allowlists without starting desktop registration.

## Mobile Markdown image resolution

Folder-backed reader stores expose their rooted `provider` and the reader's
relative `key`. The mobile host uses `commonUtils.formats.markdown.image_sources.folder_image_source`
to build a per-render image source from this pair
for both preview and formatted editing. Path normalization permits parent paths
within the provider root, rejects external/absolute paths and delegates all I/O
to the provider. Images are validated before embedding; cached entries recheck
provider revisions and credential access. LocalCrypt uses the provider's native
range/decryption stream without creating plaintext files.

The formatted editor renders images inside protected inline spans while retaining
Markdown syntax for serialization. Wiki embeds retain their exact block source.
Missing images fall back to alt text. Tests in `mobile_build/tests/editing/test_markdown_images.py`
and `test_markdown_editor.py` cover rooted paths, GIF/WebP/PNG/JPEG, encrypted-provider
reads, revoked access and source preservation. GIFs retain their complete encoded
bytes for native WebView animation. Shared image markup interprets Obsidian width
and height hints and caps image width at its containing page. Size hints stay in
the image's protected Markdown reference during surrounding paragraph edits.
`mobile_build/native_tests/tests/logisticsmobile/markdown_gif_probe.py` exercises real
iOS/Android WebViews using synthetic provider files, save/reopen and source
serialization; a native screenshot driver must verify visible frame changes.

## Notes Library ownership

`notes.py` provides toolkit-independent marker detection, rooted paths, bounded
reads and immediate-child filtering. Note reads complete short provider reads
through EOF or the 2 MiB ceiling plus one using `runtime.streams.read_up_to`, then
apply the existing size, cancellation and revision checks before decoding.
Desktop `notes_actions.py` contributes the
location command; `ui/notes_library.py` owns its lazy Documents window and
cooperative workers. Its credential observer uses a Python bound method that
emits the Qt revocation signal, because the session registry holds observers with
`weakref.WeakMethod`; a Qt signal's built-in `emit` method cannot be registered
directly. The workspace action entry carries `storage_scope` while retaining both
local and remote endpoints for transfer contributions. Notes probes only that
scope. Local viewers enable editing by default; Cloud viewers remain read-only.
`PageStorage` publishes local saves on a worker through `ResourceTextSession`,
checks original bytes and revisions, and retains drafts on failure. Navigation
and closing resolve unsaved changes before retiring the current note.
`test_notes_library_desktop.py` exercises real rclone LocalCrypt and
crypt-remote listing, nested note reads and revocation. Mobile's
`test_notes_library.py` covers both encrypted sources with the host native bridge
when `LOGISTICS_MOBILE_BRIDGE` points to its shared library, using only synthetic
credentials and an in-memory remote. Mobile resolves the same location scopes in
`mobile.notes_actions` and presents them through the retained adaptive
reader. `mobile/notes_library.py` owns that presentation through a declared
`NotesHost` contract. The host retains entry-point routing, workspace sessions,
provider resolution and credential lifetimes. The shared native private WebView
supplies memory-only rendering; Notes Library containment and URL policy remain
feature-owned.

Mobile libraries publish separate Close and page-history controls to the native
toolbar. The **×** calls `NotesHost.close_session` through the host's session-close
workflow, retiring the library even when page history or compact browsing is
active. The visible **‹ / ›** controls only navigate note history; they stay
disabled at its ends. The documentation reader uses the same controls, with
Close returning through its host route. Android system Back retains its
browse-panel, page-history, then exit ordering.

Remote providers never get a search widget or recursive index. Private note data
stays in memory and credential revocation retires the document. See the
[workspace contracts](../../../development/mobile-workspace-navigation.md#notes-library)
for lifecycle and cross-platform validation.

## Mobile new-document form

`mobile.document_choices` owns one scrollable form shared by Home,
Documents and the editor action menu. It validates the display name, adds the
selected text/Markdown extension if absent, and optionally seeds Markdown with
a first heading. Creation passes the name and UTF-8 content to the managed
document store before opening the editor; cancellation leaves storage untouched.
Validation and creation errors remain visible in the form. Home and document
lists omit redundant type subheaders while retaining state badges.

`LocalTextCopies.open` accepts an optional `read_provider` for a scoped read
adapter, such as the mobile host's byte-counting stream. It delegates the same
path, revision checks and cancellation to `ResourceTextSession`; the original
provider remains responsible for later saves. The feature does not import the
host's progress presentation.

## Native mobile editor chrome

`mobile.ui.TextEditorView` publishes native title, toolbar and button handles to
the host using the reader contract. iOS borrows the existing Save/View/Actions
buttons and centers the document name; a clean buffer omits Save. The explicit
Rename action edits the existing name control through its normal validation and
change handler, preserving document/session identity and unsaved text. Native
source inputs and formatted WebViews remain the same retained editing surfaces.

Provider Markdown records the source represented by its current preview.
Unchanged native text notifications do not reload that preview and reset its
scroll position; actual edits still schedule the existing live render. The
mobile host owns close/reopen scroll state and restores it after native drawing
and pending font/viewport reflow. WebView load hooks retain their existing
search and font handlers. Close requests use the shared host lifecycle and
prompt for unsaved edits before releasing the document session.

On iOS, retiring a Markdown WebView disables its native callbacks and queues a
replacement of the live DOM before navigating to the closed-document page.
WKWebView may defer navigation while a compact sidebar hides the article; the
old note must already be cleared independently of that navigation. Native Notes
Library checks retire a hidden article and verify that its previous text is gone.

## Shortcut save failures

Shortcut overrides retain their existing JSON mapping and global window fanout.
The editor uses shared atomic JSON publication; it restores current bindings on
filesystem, serialization or value failures and only updates other windows after
publication succeeds. Temporary validation actions are retired even if a later
mapping value is invalid. `test_text_editor_extensions.py` covers malformed
values, serialization failure, locked publication, retained saved bytes and
cross-window consistency.

## Recovery failure during close

Session suspension defers closing only after a checkpoint future exists. A
synchronous capture or worker-submission failure immediately falls back to the
ordinary Save/Discard/Cancel prompt; no nonexistent completion callback is awaited.
Executor submission errors are reported as recovery failures, and unsaved text
remains in the editor. Asynchronous write failures retain the existing retry and
normal-close fallback. `test_text_editor_recovery.py` covers both failure timings.

Recovery errors retain a nonempty failure state even when an exception supplies
no message. This prevents a failed checkpoint from restarting automatic suspension
or being treated as success; the normal close prompt remains available.


## Mobile Markdown refresh

`mobile/markdown_editor.py` owns block mapping and the native change protocol;
`mobile/markdown_script.py` owns DOM input, serialization, selection and commands;
`mobile/markdown_style.py` supplies the shared reading typography and adaptive
writing/formatting layout. They remain offline and preserve untouched source
blocks. Private provider previews and formatted surfaces use the memory-only
WebView on supported native platforms.

Formatted input is flushed from the live DOM before Save, explicit mode/reading
commands and native close decisions. A replaced or closed page rejects a late
snapshot. The existing source input remains the sole draft used by persistence,
search and recovery. Remote Markdown opens rendered even when an entry point
requests editing. `access.py` rejects remote/read-only providers and providers
without replacement capability; persistence repeats that check. Read-only and
writable sessions use distinct identities even when they share a cache root.

The Android document action bar remains visible while editing with a software
keyboard. Short windows tuck secondary rows; the primary actions still provide
Source and Formatted commands. Very short WebViews use a floating Format button
and a scrollable overlay rather than consuming another full toolbar row. Keyboard
state and active-session changes invalidate layout even when native dimensions
are unchanged, including document creation while the keyboard is open.

The Notes Library presents its location and access state, loads folders on demand,
and supplies local note creation, provider-scoped images and editing handoff.
`mobile/library_editing.py` resolves Save/Discard/Cancel before returning to the
retained browser. It refreshes the saved note and restores its reading position.
Creation uses the provider’s exclusive create operation; remote libraries reject
creation and editor invocation in handlers as well as hiding their controls.

Focused checks include the Markdown editing/font/image/search/speech suites,
`test_provider_markdown.py`, `test_markdown_access.py`,
`test_markdown_library_workflow.py`, Notes Library/Obsidian, editor picker,
keyboard/chrome, provider sessions and close/reader lifecycle regressions.
The native bridge fixture additionally exercises LocalCrypt and encrypted-remote
library reads without real credentials. Packaging and lint remain required.

`markdown_rework_probe.py` checks native formatting, final-input saving, real
rotation, library return, read-only remote policy and LocalCrypt save/lock behavior.
`editor_keyboard_probe.py` exercises actual native input connections/composition,
caret and toolbar geometry, formatting/link dialogs, new documents, 32-point text
and rotation. It accepts `--landscape` on Android. Keep raw evidence outside the
wiki. For an already built, current simulator application:

```sh
.venv/bin/python -m mobile_build.validation.markdown_rework_tools \
  --app '/absolute/path/Logistics Mobile.app' --device SIMULATOR_UUID \
  --output mobile_build/logs/markdown-acceptance
```

Add `--keyboard` for the keyboard probe. The helper stages a current source
snapshot into a separate QA app, records its source manifest and native errors,
and saves evidence before uninstalling that QA app. It never installs over the
main application. Physical-device, fold-pose and accessibility acceptance gaps
are tracked in the rework brief; host tests are not substitutes for native checks.

## Mobile live Markdown input

The mobile formatted editor consumes commonUtils' portable live Markdown syntax
rules, also used by the desktop editor. Its WebView adapter lives in
`markdown_live_script.py`; source serialization, formatting commands and the
native patch protocol remain in `markdown_script.py`. Syntax and delimiter
choices belong to the shared owner, while DOM ranges, input/composition events,
selection restoration and display spans belong to the WebView adapter.

Display spans retain typed Markdown, including incomplete syntax. Patch comparison
uses serialized content so presentation changes do not dirty untouched blocks.
Imported escaped punctuation retains its literal meaning when adjacent text is
edited. Rebuilding spans invalidates native browser undo nodes, so the adapter
retains section snapshots for typing and toolbar operations, capped at 100 entries
and approximately 8 MiB (with at least the most recent edit retained). Toolbar,
hardware shortcuts and cancelable history input events use that history. Source
mode continues to use the native text input's history.

`Python/tests/test_mobile_markdown_editing_dom.py` exercises production HTML in
Qt WebEngine with a mobile-sized viewport: character typing, headings/emphasis,
code literals, Unicode composition, repeated selection wrapping, deletion,
Undo/Redo, toolbar formatting and escaped imports. It complements the mobile
host editor/bridge tests and shared desktop live-edit tests. Browser and dummy
host checks do not certify iOS/Android keyboard behavior on physical devices.

The block-style toolbar consumes a live heading's typed prefix before applying
the requested block style. Repeated heading choices therefore serialize one
heading prefix; Paragraph removes the heading, and Quote/Code do not retain its
display size. Prefix removal and the browser command share one Undo step. Live
heading levels are refreshed after edits, including removal of inherited heading
attributes from new paragraphs. DOM regressions cover these transitions, inline
content, selected blocks, Unicode and 32-pixel base text.

Live editor caret/history bookmarks count paragraph starts and explicit line
breaks as well as UTF-16 text positions. Empty paragraphs therefore have distinct
positions from the preceding text, so Enter, Shift+Enter and Undo/Redo do not
restore the caret to the previous line when display spans are rebuilt. Whole-block
selections normalize to the equivalent position inside their leading blocks.
The production-HTML DOM suite covers following text after Enter, soft line breaks,
blank paragraphs and Undo/Redo alongside delimiter wrapping and composition.

`mobile_build/native_tests/tests/logisticsmobile/markdown_enter_probe.py` validates
these operations in the native WebView using isolated documents. On 2026-10-24,
the Boox Android run passed with real InputConnection Enter key events; the iOS
simulator run passed using WebKit's paragraph command. Both runs also checked
native multiline insertion in Markdown Source mode and plain text. This scope
does not certify every software keyboard or physical iOS keyboard. Temporary QA
apps were removed after collecting results; the main app and its data were kept.
