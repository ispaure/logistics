# Mobile Markdown editor and library rework

Implementation brief requested on October 24, 2026. Rework the mobile Markdown
editor and Notes Library into a coherent, modern reading and writing experience
on iPhone, iPad, iPhone Duo and Android phones. Fix formatted editing on iOS and
controls becoming inaccessible when the Android keyboard opens. Local and
LocalCrypt must support reading and writing; cloud remotes must remain read-only.

This is planned work. Completion requires the implementation and the acceptance
evidence below; existing guides describing intended behavior are not proof that
the reported defects are fixed.

## Execution instruction

Carry this work through diagnosis, design, implementation, refactoring and native
testing. Keep working through failed checks and visual problems until the editor
and library meet the acceptance criteria. Do not stop after a cosmetic pass,
a passing host suite, or one successful device run. If a required device or
runtime is unavailable, complete independent work and record the exact unverified
gate; do not describe the whole rework as finished. Preserve user documents,
LocalCrypt data, settings and unrelated changes in the current development branch.

## Starting points and ownership

Read the [developer index](../../../development/development.md),
[mobile runtime](../../../development/mobile-runtime.md),
[workspace navigation](../../../development/mobile-workspace-navigation.md),
[mobile handbook](../../../development/mobile-handbook.md), and
[commonUtils boundary](../../../development/commonutils-integration.md).

| Owner | Current responsibility and planned review |
| --- | --- |
| `Python/features/text_editor/mobile/markdown_editor.py` | Formatted WebView, block serialization, formatting commands, HTML/CSS and change bridge. Diagnose iOS rendering, input and synchronization before choosing the editing engine. |
| `Python/features/text_editor/mobile/ui.py` | Managed-document editor. Bring its modes, controls and lifecycle into the same interaction model as provider documents. |
| `Python/features/text_editor/mobile/provider_markdown.py` | Provider Markdown modes, rendering, source synchronization and controls. Retain one authoritative draft and guarded asynchronous rendering. |
| `Python/features/text_editor/mobile/notes_library.py` and `notes.py` | Library navigation, note reading, provider bounds and editor handoff. Rework presentation and preserve bounded folder loading and containment. |
| `Python/mobile/provider_*.py`, `editor_picker.py`, composition and session owners | Opening, access policy, saving and lifecycle. Enforce storage permissions beneath the controls. |
| `Python/mobile/keyboard.py`, native host adapters and shared adaptive components | Keyboard geometry, safe areas, native bars and allocated pane sizes. Fix the responsible layout owner rather than adding competing offsets. |

Keep Logistics storage policy, document lifecycle and feature presentation in
Logistics. If reusable editor or adaptive mechanisms need changes in commonUtils,
read its own `AGENTS.md`, test that repository and document its APIs there. Keep
the parent dependency update explicit. Avoid broad unrelated navigation changes;
preserve `DestinationRail.tools_menu` and the existing Misc glyph.

## Storage and write permissions

Use one explicit access decision shared by editor and library entry points.
Derive it from the selected storage location and provider capabilities, not the
display label, the existence of a download/cache, or whether the provider is private.
An encrypted cloud remote is still a remote; LocalCrypt is an editable local copy.

| Location | Required behavior |
| --- | --- |
| Local | Read, formatted edit, source edit and save back to the selected local file. Allow creating a note in a writable library folder. |
| LocalCrypt | The same editing workflow while unlocked, saving through the encrypted local provider. Locking or changing credentials invalidates pending work and retires private surfaces according to the existing privacy contract. |
| Cloud remote, including encrypted remotes | Read rendered Markdown, navigate notes and search the open note. Optional source inspection is read-only. No edit, create, replace, rename, delete or save-back operation from these Markdown surfaces. |

Enforce remote restrictions in command handlers and persistence paths as well as
menus and widgets. A direct callback, restored session or stale WebView message
must not bypass them. Reuse existing authorized local-copy/export workflows if
offered; a copy must be explicitly created as a separate local document before
editing. Preserve existing privacy restrictions for LocalCrypt exports.

## Reading and writing design

Create representative native previews before spreading the layout through both
hosts. Establish typography, spacing, semantic colors, selected states and icon
treatment that fit the existing mobile app. Review light and dark themes at phone
and tablet sizes. Avoid stacked toolbars, unexplained icons and dense desktop controls.

- Use clear Read, Formatted and Source modes with an unmistakable active state.
  Opening a note reads it; entering Formatted must show styled, directly editable
  content. Source must expose the exact Markdown syntax.
- Keep the note title, navigation, mode access, save state and actions coherent
  across standalone documents and library notes. Show a clear read-only state for
  remotes. Save feedback must distinguish unsaved, saving, saved and failed.
- Put common formatting within easy reach: headings, bold, italic, lists, links,
  quotes, code, undo and redo. Place secondary tools in an accessible sheet or menu
  that fits the remaining viewport. Preserve the selection when using controls.
- Support blank-note tapping, caret placement, selection handles, long-press
  editing, paste, autocorrect, dictation and composition input. Mode changes must
  not lose the latest input, unexpectedly move the caret, or reset reading position.
- Render unsupported or source-only syntax honestly, with an obvious route to
  Source for editable locations. Never silently flatten or discard it. Keep source
  inspection read-only on remotes.
- Keep tables and code readable with contained horizontal scrolling. Preserve
  relative images, links, wiki links and frontmatter within their current supported
  contracts, with useful loading/error states.

## Keyboard and adaptive layout

Make usable space come from the actual window or pane and keyboard occlusion.
Assign one owner to each inset and one primary scroller to the writing surface.
Account for safe areas and visual viewport changes without applying keyboard
clearance twice. Essential controls must remain reachable while typing; controls
may move into a reachable menu rather than simply disappear.

- Android: reproduce the reported failure with a real software keyboard, including
  landscape, a tall suggestion row, enlarged text and both gesture and button
  navigation where available. Verify formatting, settings/actions, mode access,
  Save and keyboard dismissal remain usable.
- iPhone: validate actual WKWebView rendering and touch input, notch/home-indicator
  clearance, keyboard transitions, selection and formatting with the keyboard open.
- iPad: support full screen, narrow multitasking windows, rotation, floating/docked
  keyboards and hardware keyboards. Choose library sidebar versus drawer from the
  available pane width.
- iPhone Duo: use the dedicated runtime and existing pose tooling. Test outer and
  inner displays, supported folded/partially open/flat states, and transitions
  during an unsaved edit. Respect the seam and retain document, selection and mode.
- All targets: keep the caret visible during sustained typing and Enter, permit
  intentional scrolling away from it, and avoid jumping on each keystroke. Test
  keyboard open/close, mode switching, menus and rotation in combination.

## Notes Library redesign

Use the same reading surface, typography, actions and access rules as standalone
Markdown. Give the library a clear location title and Local, LocalCrypt or Remote
context, a legible folder/note list, selected-note state and useful empty, loading,
locked and error states. On phones, use focused list-to-note navigation; on wider
panes, use a resizable or appropriately bounded sidebar and detail view.

Preserve navigation history, list position, note position and active filename
when opening an editor and returning. Refresh the rendered note and relevant list
entry after a successful save. Test unsaved navigation through Save, Discard and
Cancel. Provide note creation for writable local libraries; show no mutation
commands for cloud libraries. Keep filename filtering distinct from searching the
open note, and retain bounded, on-demand remote traversal rather than introducing
an unrequested full-vault scan.

## Implementation sequence and refactoring

1. Reproduce both reported defects with a small shared Markdown fixture. Record
   platform, entry point, access location, mode, dimensions and keyboard state.
   Trace iOS load/style/input/bridge events and Android inset/bar ownership. Turn
   confirmed failures into meaningful regressions before changing their owners.
2. Compare repairing the existing block editor with adopting a maintained editing
   engine. Prototype the hardest iOS input, selection, Markdown preservation and
   Android keyboard cases. If considering a dependency, evaluate offline bundling,
   licensing, accessibility, payload cost and private-document behavior. Choose on
   observed results; avoid a migration that cannot preserve source safely.
3. Establish the shared access decision and test it across every opening path.
   Centralize mode and command availability without moving storage ownership into
   WebView JavaScript or duplicating the draft.
4. Refactor editor document state, rendering/input bridge and presentation into
   focused owners. Separate HTML/CSS/JavaScript assets where it improves maintenance.
   Give managed and provider hosts a common presentation contract. Make load,
   ready, editing, saving, failure, suspend and close transitions explicit; flush
   final input before mode changes, save or navigation. Reject stale revisions and
   callbacks after close, lock or provider changes.
5. Implement the approved visual direction and keyboard layout in both editor
   hosts, then integrate the library redesign and save/return workflow. Remove
   obsolete duplicate layout code after equivalent behavior is verified.
6. Run focused tests, native interaction and visual review across the matrix
   below. Fix failures and repeat affected checks. Review the complete user flow,
   not only isolated controls. Update usage and developer guides to the final
   implemented behavior.

## Testing and acceptance

Extend the existing suites: `mobile_build/tests/editing/test_markdown_editor.py`,
`test_provider_markdown.py`, `test_source_editor.py`, Markdown image/search/font
tests, `mobile_build/tests/documents/test_notes_library.py`, `test_editor_picker.py`
and relevant session/privacy tests. Use existing native editor, keyboard and
rotation probes as starting points; add reusable drivers under their test owner.
Run shared component tests only where the changed mechanism requires them, and
retain desktop editor/library regressions when touching shared behavior.

| Target | Required native coverage |
| --- | --- |
| iPhone | Portrait/landscape, software keyboard, touch formatting and selection, real formatted rendering, light/dark, enlarged text. Include a physical iPhone run when available. |
| iPad | Portrait/landscape, narrow and wide windows, sidebar/drawer transitions, docked/floating and hardware keyboards. |
| iPhone Duo | Dedicated Duo runtime, outer/inner displays and supported poses, folding/rotation during editing, seam-aware layout. Ordinary iPhone emulation does not satisfy this row. |
| Android phone | Compact and tall screens, portrait/landscape, actual software keyboard and suggestion row, navigation insets, large text. Include physical-phone verification of the reported overflow when available. |

Exercise each target with standalone Local, standalone LocalCrypt, local library,
LocalCrypt library and remote library/file routes. Cover blank, short, long and
mixed-syntax notes, rapid mode changes, save failure, external modification,
background/resume and closing while work is pending. Use focused combinations
after broad route coverage so each layout and storage risk has explicit evidence.

Acceptance requires all of the following:

- Formatted mode visibly renders and edits headings, emphasis, lists, links, quotes,
  code and supported tables on iOS and Android; there is no source-like fallback
  mislabeled as Formatted. Native typing, paste and composition actually update
  the saved Markdown.
- Read → Formatted → Source → Read → Save → reopen preserves intended content,
  untouched syntax and Unicode. A no-op mode round trip does not rewrite the file.
  Undo/redo remains coherent; unsupported blocks and document-size limits are explicit.
- Every Local/LocalCrypt route can edit and save, and every remote route rejects
  mutations even when handlers are invoked directly. Tests assert zero remote
  writes and no plaintext LocalCrypt artifacts escaping its existing privacy boundary.
- The keyboard never pushes essential actions irretrievably out of view. Visual
  inspection and geometry assertions confirm reachable controls, visible caret,
  unobscured dialogs and no accidental outer-page scrolling in constrained layouts.
- Library navigation and editor handoff retain context; saved changes appear on
  return, failed saves retain the draft, and Cancel prevents destructive navigation.
- VoiceOver/TalkBack labels, focus order, text scaling, contrast and platform-sized
  touch targets remain usable. Opening formatting controls does not lose selection.
- Loading, typing, scrolling and mode changes stay responsive on representative
  long notes. Record timings and inspect repeated open/close for leaked WebViews,
  tasks or memory growth; investigate regressions against the initial baseline.

Store screenshots, recordings, geometry reports and timings under ignored
`test-results/` or `mobile_build/logs/`. Keep public documentation limited to a
concise validation scope, without links to local-only evidence. Report separately
what passed host tests, simulator/emulator interaction and physical-device review.
If BOOX testing is included, save evidence and uninstall temporary Logistics test,
probe and QA packages afterward. Verify only `io.github.ispaure.logisticsmobile`
remains among Logistics packages; preserve that main app and all its data.

The final handoff must name the changes, tests, device matrix results and any
remaining acceptance gaps. Mark complete only after all required gates are met.
