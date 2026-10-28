# iPhone Duo UI conventions and implementation brief

Prepared October 28, 2026. Scope: Logistics on iPhone Duo, with iPhone, iPad and Android regression checks where shared code changes.

Logistics should keep familiar horizontal navigation on the **opened inner display in portrait**, and let native bars adapt to the side on the **opened inner display in landscape**. In system two-app Split View, Logistics should use its window's outer edge: left when it is the left app, right when it is the right app. The reported document buttons remaining across the top in opened landscape are the first reproduction target. A horizontal control is not automatically a defect: its container and representation matter.

The action plan below remains the acceptance contract. The October 28 implementation results at the end record the fixes and their verification scope; two-app system Split View and the remaining hardware/accessibility cases are separate acceptance gates.

## Apple guidance and the placement decision

### Expected placement by configuration

| Configuration | Expected native navigation and action placement | Logistics acceptance target |
| --- | --- | --- |
| Open inner display, portrait | Standard horizontal bars. | Back or Close and a browse toggle remain discoverable; title and actions fit without overlap. |
| Open inner display, landscape, one app | Eligible bars move to the side, normally the right edge. | Document actions participate in the native vertical bar instead of remaining in a custom top row. |
| Open inner display, landscape, Logistics in left system window | Controls use the left outer edge. | No forced right rail or central seam obstruction. |
| Open inner display, landscape, Logistics in right system window | Controls use the right outer edge. | Same action semantics and availability as the left window. |
| Closed outer display | Side controls also apply; portrait alone does not imply horizontal bars. | Verify both supported outer-display orientations and short-height overflow. |

Apple describes the portrait exception and the outside-edge rule in [Designing for iPhone Duo](https://developer.apple.com/design/human-interface-guidelines/designing-for-iphone-duo). These rules concern native bars; body controls still belong to their task.

**System Split View means two separate apps.** Logistics' own browser/document split and paired documents are internal panes. They do not each acquire an outside device edge. Apple limits vertical participation to eligible edge containers; in native split views the detail column participates while other columns can remain horizontal. Centered inner-display sheets can retain horizontal bars. Right-to-left content does not itself swap the hardware-aligned vertical bar. See [Raise the bar with iPhone Duo](https://developer.apple.com/videos/play/tech-talks/111462/), particularly 3:09–5:56.

### Portrait navigation conventions

Use leading placement for navigation and trailing placement for contextual tools. Back follows hierarchy; Close dismisses the current presentation. A hamburger reveals a collection or drawer, and an ellipsis exposes additional actions. Keep these meanings distinct and use standard symbols. Avoid crowding the title or presenting two controls for the same return action. Apple's [Toolbars guidance](https://developer.apple.com/design/human-interface-guidelines/toolbars) distinguishes navigation, actions and destination switching and recommends standard Back and Close controls.

For Logistics, retain the existing document Close contract, including its save/discard/cancel choices. That contract closes a session; it must not silently become a generic route pop. Audit whether each secondary panel instead needs Back, Cancel or Done. A browse button beside document Close is acceptable when it performs a separate action and remains clearly labeled for accessibility.

### Native adaptation and exceptions

Prefer bars owned by navigation and tab containers. Supply symbols and meaningful titles; consolidate overflow and use semantic groups and visibility priorities. Text-only items and custom views may stay horizontal. Preserve meaningful status text and keyboard accessories in their appropriate context. These are reasons to inspect individual items rather than force every button onto a vertical axis. See [Raise the bar with iPhone Duo](https://developer.apple.com/videos/play/tech-talks/111462/), 5:56–14:21.

Build with iOS 27.1 or later for the full adaptive-bar behavior. Derive layout from current window/view geometry and safe areas, and retest after resizing or folding; device names and orientation checks cannot establish available space. Apple distinguishes the SDK compatibility behaviors and identifies the Duo simulator as the best native-experience test in [Prepare for iPhone Duo](https://developer.apple.com/iphone-duo/prepare/).

UIKit's [verticalBarEdge](https://developer.apple.com/documentation/uikit/uitraitcollection/verticalbaredge) reports the system's preferred edge even if a vertical bar is not visible. A nonzero trait is therefore useful input, but **does not prove that the current controller's buttons actually moved**. Acceptance must inspect native bars and item frames. Safe areas, current allocation, text sizing and localization also matter; see Apple's [Layout guidance](https://developer.apple.com/design/human-interface-guidelines/layout).

## Current Logistics assessment

The five mobile destinations are Home, Workspaces, Documents, Chat and Settings, declared in [navigation.py](../../Python/mobile/navigation.py). The audit also covers their child screens, document formats, transient controls and native presentations.

| Existing owner | Verified source behavior | Implementation consequence |
| --- | --- | --- |
| [ios_toolbar.py](../../Python/mobile/ios_toolbar.py) | Creates ordinary native bar items, semantic groups, leading actions, prominent pinned actions and live system overflow. Reads `verticalBarEdge`. Save deliberately has a text representation. | Extend this owner where needed; diagnose actual axis and containment before rewriting it. A visible horizontal Save alone does not prove failure. |
| [workspace_navigation.py](../../Python/mobile/workspace_navigation.py) | Projects reader controls into the active destination controller; detaches their old content toolbar; caches projections including bar-edge state; mounts document Close and browse actions. | Trace controller selection and refresh for each entry path, document switch and pose. Check for stale actions on retained tabs. |
| [adaptive_workspace.py](../../Python/mobile/adaptive_workspace.py) | Provides a native split-controller implementation. The active `WorkspaceNavigation.install` override currently retains destination navigation stacks and measured internal panes instead. | Inspect the actual runtime hierarchy; do not assume the base class's split-controller installer ran. Distinguish internal pane controls from document actions. |
| [ios_workspace_columns.py](../../Python/mobile/ios_workspace_columns.py) | Uses a custom controller to host a sidebar beside folder navigation. Document routes hide the sidebar and enlarge the navigation frame. | Prioritize actual document-opening and return geometry here. Custom containment is a hypothesis to investigate, not an established cause. |
| [ios_reader_chrome.py](../../Python/mobile/ios_reader_chrome.py), [fold_layout.py](../../Python/mobile/fold_layout.py) | Observe native viewport changes and use window-local reserved fold regions. | Check bar-axis changes even when content size is unchanged; retain fold, fullscreen and privacy behavior. |
| [SDK selector](../../mobile_build/select_ios_sdk.py) | Defaults to the 27.1 SDK series for repeatable validation. | Record the SDK linked into the tested app as well as simulator/runtime versions. Source configuration cannot identify the user's installed build. |

The [existing toolbar validation record](mobile-workspace-navigation.md#adaptive-ios-toolbar-actions) describes an October 21 run of 27 screen states on each of Duo, iPhone and iPad. It explicitly excludes inner-display fold poses, accessibility settings and live remote providers. Keep that scope distinct from the new acceptance matrix below.

### First diagnostic pass

1. Record app version, source revision, linked SDK, runtime, display, window position and entry path. Reproduce a document from Documents and from Workspaces separately.
2. Capture the actual controller hierarchy, navigation item owner, preferred vertical edge, safe insets, bar frames and visible item frames before opening, after opening, and after rotation.
3. Determine whether the remaining top controls are native items, text-only/custom representations, an interior pane toolbar, or a detached toolbar that was mounted again. Check whether the navigation container reaches the eligible window edge.
4. Compare direct cold launch in opened landscape with portrait → landscape. Repeat in both system Split View positions. Do not infer system-window placement from an internal two-pane layout.
5. Check active-controller resolution and resize/trait invalidation. Correct the owning mechanism only after the failing path is identified; retain working horizontal behavior and older-platform fallbacks.

## Action plan for each panel

Each row is a required work item. Inspect first, change only demonstrated gaps, and double check that panel immediately after any change using the verification procedure below. A verified no-change outcome is valid. Record separate results for distinct formats, sources and child screens rather than marking an entire family passed after one screenshot.

### Destinations and browsing

| Panel | Required action | Panel completion check |
| --- | --- | --- |
| App navigation shell | Check native tab/side adaptation and active destination through cold launch, fold and system Split View. Preserve the existing policy that hides destination navigation while a document is open. | Switch through all five destinations; selected icon, route and toolbar agree. Closing a document restores the intended shell. |
| Home | Audit its top actions, unlock shortcut, notices and two-column content. Keep Open/New and recent-file row actions associated with their content. | Open a document and return; verify no duplicate headings, stranded bar items, clipped controls or lost Recent selection. |
| Workspaces overview | Audit Transfers/Refresh, folder tree, source selectors, expandable groups and empty/locked states. Verify sidebar/detail allocation in portrait and landscape. | Expand a folder, open actions, rotate and return; preserve selection and independently usable scrolling. |
| Workspace action detail | Separate native Back from Browse/Pull/Push/destructive body actions. Ensure long source names and notices fit the current pane. | Back affects the detail only; destructive actions keep confirmations; compact/wide transitions preserve the selected folder. |
| Local file browser | Audit parent Back, title, Search, Sort, List/Tiles and selection controls in the native folder bar. Remove duplication only if demonstrated. | Traverse nested folders, search, open a file, close it and retrace folders. Correct document actions replace and then restore browser actions. |
| LocalCrypt and Remote browsers | Repeat browser checks for each source; check loading, unavailable, locked and error states. Preserve source identity and access guards. | Rotate during loading and after opening a supported document; no stale provider menu, exposed private filename after locking, or accidental operation. |
| Open/import picker | Check Cancel and folder navigation independently of the underlying document. Respect native presentation behavior. | Cancel from a deep folder restores the same draft and mode; document selection does not duplicate sessions. |
| Documents hub | Audit search, All open/Recent/Saved sections, New/Open commands and row Close buttons. Body row controls stay with their rows. | Search and clear, reopen and close sessions; labels and controls remain reachable in every allocation. |
| Documents browse drawer | Check the hamburger's native position and accessible name, compact dismissal and wide list/detail behavior. | Open/close, select a file, rotate, narrow and widen; retain the same document and browse history with no duplicate toolbar. |
| Books and Comics library | Audit search, folder selection, Back and reader return. Treat this list separately from an opened book. | Open a book/comic from a folder and return to that folder with its state retained. |

### Document panels and their tools

| Panel | Required action | Panel completion check |
| --- | --- | --- |
| Text editor | Prioritize Close, browse, Find, Save and overflow. Confirm native ownership and distinguish intentional text-only Save from a custom horizontal toolbar. | Type a draft, rotate, open overflow with one tap, save, then close with save/discard/cancel paths. Each action targets this document. |
| Markdown editor and preview | Audit both modes and their distinct controls; follow [preview.py](../../Python/mobile/preview.py) and editor owners. | Edit → Preview → Edit across poses retains unsaved text, reading position and the correct mode actions. |
| Find and Replace | Keep search fields and keyboard accessories attached to the editing task. Adapt width and overflow without moving input fields into a side bar. | Search, next/previous, replace and hide controls; keyboard appearance/dismissal does not cover the result or strand Close/Save. |
| Paired documents | Check active pane ownership, browse replacement and collapse/restore. Apply the interior-pane exception instead of forcing two device-edge rails. | Edit both drafts, switch active pane, invoke each pane's commands, narrow/widen and close one. No action operates on the other document. |
| Notes Library | Audit tree/browse toggle, note history, editing and preview controls independently from ordinary Markdown. | Navigate links and history, edit, open browse and rotate; maintain the correct note, draft and return path. |
| Documentation reader | Audit Close, browse, page Back/Forward, Find, speech and overflow in [documentation_ui.py](../../Python/mobile/documentation_ui.py). Distinguish page history from leaving help. | Follow multiple links; history buttons traverse pages, Close leaves help, and browse stays reachable after reflow. |
| EPUB reader | Audit Contents/bookmarks, appearance, Find, speech, Close and overflow across imported and provider readers. | Open each tool, rotate and return to the same chapter/anchor. Verify fullscreen exit restores correct actions. |
| Comic reader | Audit previous/next, fit, page list, appearance and fullscreen; preserve semantic navigation grouping. | Change pages in both directions, fold/unfold and toggle fullscreen. No control enters a reserved fold region or remains hidden on exit. |
| PDF reader | Audit tools, page navigation, search and Close for every supported opening path. Keep page controls and results usable inside their pane. | Search and jump pages, open/close tools, rotate and return; page and zoom remain stable and controls avoid native chrome. |
| Image preview | Audit previous/next, fit/zoom and menu controls; preserve the existing image-specific edge expansion policy. | Pan/zoom, rotate and leave preview; action hit regions remain usable and ordinary text/forms regain safe insets. |
| Notebook library and canvas | Separate document navigation/completion from pen, eraser, page and canvas tools. Inspect the host controls in [mobile_notebooks.py](../../Python/services/documents/mobile_notebooks.py) and the [notebook panel](../../Python/features/notebooks/mobile/panel.py). | Draw, change tool/page, resize, export and close/reopen. Pen targeting, document identity and ink survive layout changes. |
| Loading, failed-open and private reader states | Audit cancel/retry, status and toolbar replacement for the document families above. Cover managed and provider text/Markdown, EPUB, comic, PDF and image paths where supported. | Cancel loading and retry failure; lock or background private content. No orphan bar item targets a disposed or concealed owner. |
| Reader child pages | Enumerate Contents, bookmarks, appearance, metadata, search results, speech and page pickers actually reachable for each format. Give each its own acceptance row. | Back/Done returns to the originating reader with its state; centered sheets may retain horizontal bars without being recorded as failures. |

### Chat, settings and operational panels

| Panel | Required action | Panel completion check |
| --- | --- | --- |
| Chat | Check the declared native conversation toggle, New and actions menu in [LM mobile UI](../../Python/features/lm/mobile/ui.py). Keep composer/send and attachment controls with the composer. | Switch conversations, preserve unsent drafts, rotate with keyboard, open overflow and return from configuration. No test should require a live model request. |
| Conversation drawer and chat configuration | Audit compact/wide drawer access, selection, Back and form completion. Avoid duplicate custom and native header actions. | Open/close drawer and configuration on both system-window sides; correct conversation and draft remain active. |
| Settings categories and detail | Check native Back and category/detail containment; resize long labels and values. Keep switches and setting-specific actions within the form. | Visit every visible category and nested page, rotate and return; selection and values persist and horizontal interior controls are classified correctly. |
| Connections and credential forms | Audit Cancel, Save/Done, password/ZIP picker, connection help and error presentation. Never promote destructive body buttons into primary completion slots. | Use fixtures; cancel and validation failure retain expected state. No passwords or private paths enter captured evidence. |
| Storage, saved files, reset and developer/help pages | Inventory all reachable Settings child pages and their confirmations. Make completion/navigation controls consistent. | Exercise harmless fixture actions and cancellation; verify safe widths and return paths. Reset/delete execution is unnecessary to test placement. |
| Transfer list, detail and review | Audit Back/Cancel, prominent review confirmation, long source/destination labels, progress and overflow. Preserve meaningful status text when its representation stays horizontal. | Cancel a fixture review without executing it; leave active-transfer details without stopping work; no toolbar migration starts or confirms a transfer. |
| Alerts, sheets, popovers and menus | Keep native presentation ownership and anchoring across pose changes. Check actual sheet placement before requiring a side bar. | Present, rotate/resize, dismiss and reopen; one usable menu appears and focus returns to its trigger. |
| Floating speech and transient overlays | Keep playback controls associated with playback and clear of keyboard, safe edges and fold regions. | Move between reader and tools, resize and hide overlay; speech state remains correct and document navigation remains reachable. |

Use [mobile runtime owners](mobile-runtime.md), [workspace navigation](mobile-workspace-navigation.md) and the owning feature guides to expand the inventory. Any reachable screen discovered during implementation must be added to the acceptance ledger before the audit can close. Retain `DestinationRail.tools_menu` and the Misc glyph reserved by repository instructions.

## Implementation order

1. **Establish the failing native path.** Complete the diagnostic pass and record the placement matrix for one text document opened from Documents and Workspaces. Include direct launch and rotation, not just resize simulations.
2. **Correct shared ownership and refresh.** Fix demonstrated controller containment, item projection, trait refresh or safe-area issues in their existing owners. Keep reusable shared mechanisms in commonUtils and document their APIs there; describe only the Logistics integration here.
3. **Complete navigation destinations.** Work through shell, Home, Workspaces, browsers, Documents and drawers. Verify each changed panel before moving on.
4. **Complete documents.** Start with text/Markdown, then paired documents, Notes/help, EPUB/comics/PDF/images and notebooks. Verify provider variants and reader child pages separately.
5. **Complete remaining panels.** Finish Chat, Settings, connections, transfers and transient/native presentations. Record justified horizontal exceptions with their owning container or item representation.
6. **Run the complete audit.** Recheck all panels together, reconcile the ledger and update the user/developer guides to describe only implemented and verified behavior.

A shared fix may resolve many rows, but it does not waive their individual verification. Keep the current development branch unless concurrent or experimental work creates a concrete reason for isolation.

## Required AI double check after every panel change

**The implementing AI must double check each changed panel immediately after the change.** It must inspect the resulting UI, exercise its controls, and compare the result with this brief before marking that panel complete. Reading code, passing dummy-backend tests, or observing a nonzero edge trait is insufficient native validation.

For every changed panel:

1. Run focused host regressions for its behavior and the shared mechanism changed. Extend existing tests when a substantive defect needs regression coverage; avoid snapshot checks that merely repeat implementation details.
2. Build and deploy with `logistics_build/build_project.py`, `build_manager/` and the owning iOS helpers. Verify the installed artifact contains the tested change and record its SDK/runtime/source identity.
3. Open the panel in inner portrait, inner landscape, and each left/right system Split View position. Also exercise outer-display presentation. Use the actual Duo simulator/native device for bar-axis and system-window behavior.
4. Inspect both appearance and interaction: button frames and hit regions, safe areas, title, ordering, grouping, overflow, enabled state, accessibility names and the actual target document. Tap controls; a screenshot cannot prove dispatch.
5. Rotate/fold while the panel is already open, then reverse the transition. Where relevant, show/hide keyboard, open/close drawer, change document and switch tabs. Confirm no duplicate headers, detached actions, lost drafts, stale menus or incorrect Back stack.
6. Check light/dark appearance, large text, VoiceOver order/labels, Reduce Motion, Reduce Transparency and right-to-left content. Keep existing 48-point app targets where used and inspect actual native hit regions rather than shrinking targets to fit.
7. Review the new diff against this panel's requirements and its neighbors. Record pass/fail/blocked and the exact remaining issue. Correct failures and repeat affected checks before proceeding.

Start focused testing through `python3 dev.py test mobile <test_file.py>`. Relevant existing owners include `test_ios_toolbar.py`, `test_ios_bar_controls.py`, `test_reader_toolbar_projection.py`, `test_ios_workspace_columns.py`, `test_ios_viewport.py`, `test_fold_layout.py` and each feature's tests. The existing [toolbar probe](../../mobile_build/native_tests/tests/logisticsmobile/ios_toolbar_probe.py) is a starting fixture; extend native checks for the new inner-display and system Split View cases rather than treating its historical scope as sufficient.

### Acceptance matrix and evidence

Maintain an ignored ledger with one row per panel, child screen, relevant source variant and configuration. Record revision/build, entry path, pose/window side, expected placement or justified exception, observed frames/interaction, evidence location, result and unresolved issue. Use **passed**, **failed**, **blocked**, or **not applicable with reason**. A missing runtime or physical device remains blocked; it cannot be converted to passed by a host test.

Every panel needs the five principal contexts in the placement table. Add outer landscape, both supported landscape rotations, partial-fold reserved regions, keyboard-visible layouts and accessibility configurations where relevant. Shared-shell changes require checking all destinations and document return paths again. Test a conventional iPhone and iPad after shared iOS changes, and focused Android flows after changes to shared Logistics presentation logic.

Keep screenshots, recordings, native frame reports and the ledger under ignored `test-results/` or `mobile_build/logs/`; public wiki pages must not link to local evidence. Use fixture documents/providers and preserve reusable probe drivers in their owning test directories. Use retention-managed scratch contexts for disposable probes and the manager's owned simulator cleanup. Record temporary devices/packages and remove them after saving evidence; preserve the main app and user data. If Boox regression testing occurs, perform the repository's mandatory test-package cleanup and verify only `io.github.ispaure.logisticsmobile` remains among Logistics packages.

## Final review for inconsistencies and omissions

**After all panel changes, the AI must look back over everything done and perform a fresh review across the whole application.** This is a separate acceptance step after individual panel checks.

- Reconcile the runtime screen inventory, this plan, changed files and acceptance ledger. Account for every discovered panel and child screen; explicitly list blocked cases and intentional horizontal exceptions.
- Compare navigation meanings, symbols, grouping, titles, menu contents and completion actions across panels. Confirm hamburger, ellipsis, Back and Close do not change meaning unexpectedly.
- Repeat complete journeys: Home → picker → editor → Preview → Save/Close; Workspaces → nested folder → document → tools → folder; Documents → pair → browse → collapse/restore; library → reader → tools → fullscreen/exit; Chat → configuration → conversation; Settings → nested help/connections → return; transfer review → cancel.
- Run those journeys through portrait/landscape, fold/unfold and both system-window positions. Cold-launch selected panels directly in opened landscape and compare with rotated results. Check keyboard and privacy restoration, not just final still frames.
- Review shared changes for effects on previously checked panels, iPhone/iPad and Android. Re-run the affected acceptance rows whenever a later shared change could invalidate them.
- Check documentation against final behavior, links and terminology. Keep raw evidence out of the wiki and preserve the root README's existing Ally Tools boundary.
- Deliver a concise implementation report listing actual changes, native and host validation scope, remaining failures/blockers and cleanup status. Do not claim complete convention compliance while required cases remain unverified.

Completion means the reported landscape document issue is resolved in the correct native container, portrait remains conventional, both system Split View sides work, every panel row has evidence or a clearly stated blocker, and the final review finds no unresolved inconsistencies within the verified scope.

## October 28 implementation results

Four changes address shared ownership and adaptation rather than introducing separate layouts for every panel:

- Workspaces navigation now reaches its owning container's outside edge. Browser detail extends through the native bar reservation; opened documents and their child routes use the full navigation frame. Content containers still apply safe-area insets. Regression checks cover document/tool opening, browser restoration, asymmetric insets and keyboard return.
- Reader projection owns Close and Browse together. Workspace headers no longer overwrite those items on subsequent renders. A native baseline reproduced the missing Close button after opening an editor in Documents or Workspaces; a subsequent native run retained both controls in each path. This also restores retained reader/help dismissal controls affected by the same competing writer.
- Unchanged native action groups and overflow providers are retained during layout callbacks. The projection checks the actual groups on the navigation item before reusing them, so a different screen's actions cannot be mistaken for the current owner's controls. Changed menus, enabled state and bar edge still refresh the projection.
- Native viewport invalidation includes the preferred bar edge, allowing controls to refresh when the edge changes without a width, height or inset change.

Final native acceptance passed **607 recorded screen states**: 112 each on the fully opened Duo, a conventional iPhone and an iPad; 120 in the actual partial-fold configuration; 120 additional child-panel states in dark appearance with enlarged system text; and 31 on the closed Duo. The rotation sweeps include portrait and both landscape directions. Main-panel runs verified Search and Save target dispatch and retained Close/Browse after refresh. The partial-fold run observed the real reserved fold region and verified document entry paths through both landscape directions. These runs use restaged current Python sources in an existing simulator shell linked with the iOS 27.1 SDK; they are not a new signed release or a physical-device installation.

The reusable [toolbar conventions probe](../../mobile_build/native_tests/tests/logisticsmobile/toolbar_conventions_probe.py) records native controller frames, preferred edges, item labels, screenshots and route/content identity across rotation. The [runner](../../mobile_build/validation/toolbar_conventions_tools.py) uses retention-managed scratch, a separate QA bundle and owned disposable simulators, saving evidence before cleanup. Its optional `--duoctl`/`--pose` arguments accept an explicitly supplied simulator-only tool; no private simulator interface is shipped in Logistics. Local fold automation used the reviewed [duoctl source](https://github.com/skarol/duoctl), with helper source hashes retained in ignored evidence.

### Panel review outcomes

| Panel family | Verified scope and disposition |
| --- | --- |
| Shell, Home, Workspaces and Documents hubs | Native presentation and rotation; host checks for folder actions, selection, ancestry and retained destinations. The navigation-frame correction applies to wide Workspaces. |
| Local browser and document entry paths | Native Search dispatch, editor opening from both tabs, repeated refresh and browser/document ownership; host search/history and return checks. |
| LocalCrypt and Remote | Native synthetic provider reader presentations and host access/privacy regressions. Actual encrypted/remote browser operations remain a live-provider gate. |
| Text, Markdown, Find, drawer and paired documents | Native presentation/rotation, Search/Save dispatch and Close/Browse ownership. Host tests cover replacement, preview/draft retention, pairing and exit guards. |
| Notes Library and documentation | Native article/library/help presentation and rotation, including retained dismissal controls; host history/navigation checks. |
| EPUB and comics | Native readers, appearance, contents/pages and metadata; EPUB search and floating speech controls. Host reading, navigation and provider regressions. |
| PDF and image preview | Native presentation and rotation; host reader/navigation and safe-area geometry checks. Physical pan/zoom remains separate. |
| Notebook | Native canvas presentation and rotation, with host panel/storage checks. Physical pen input is outside this pass. |
| Chat and conversation/configuration views | Native presentation, New-conversation dispatch and configuration controls; host loopback tests cover sending, stopping and draft retention. |
| Settings and child forms | Native category pages, connections, credential-import form, SMB form, saved files and reset review. No connection, transfer or reset was executed. |
| Transfers | Native list/settings presentation; host review/execution guards. Live progress and confirmation presentations remain a separate native scenario. |
| Loading, failure, private concealment, picker and reset behavior | Focused host checks; ordinary creation-picker presentation is also in the native sweep. Error branches, native system alerts and physical interaction require their own scenario. |
| Accessibility and appearance | Additional native child-panel sweep passed 120 states in dark appearance with enlarged system text. Full VoiceOver, RTL and motion/transparency-setting coverage remains outstanding. |

The focused host validation passed 350 tests across these owners, including the new ownership, group-retention and preferred-edge regressions. Lint and documentation-link checks also passed. The final review retained the distinction between contextual body controls, text-only Save, native navigation and system-window placement; it did not force formatting tools or meaningful text into a side bar. Every audit-owned simulator was removed, and the QA app was verified absent from the preserved existing Duo simulator. The main app was not replaced. Changes remain uncommitted on the existing development branch.

### Remaining acceptance

Automated home gestures, including a paused drag, did not establish genuine two-app Split View. The QA window stayed full-width, and the run correctly failed its width/edge assertion. **Left and right system Split View remain unverified**; internal paired documents and a left-edge bar on the rotated outer display do not satisfy this gate. The user deferred hands-on simulator assistance, so this requires a later actual system-window check.

Native live-provider operations, physical touch/VoiceOver, minimum iOS 15 behavior and the complete Reduce Motion/Reduce Transparency/RTL matrix also remain separate checks. Synthetic provider presentations and focused host regressions protect the changed ownership paths without claiming live-service or physical-device acceptance. Android collection-drive relocation is not an iOS panel and remains under its Android owner.
