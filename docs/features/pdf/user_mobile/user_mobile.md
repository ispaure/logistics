# Mobile PDF Reader

Open a PDF from a local, remote or unlocked LocalCrypt folder. Tap the fullscreen page for controls. Scroll, use page arrows, or enter a page number in **Pages & search → Page** and tap **Go**. On iOS, drag and release the side slider to jump. Pinch to zoom.

To add ink, choose **⋯ → Duplicate as .rmdoc to annotate**. This creates a same-named notebook beside the PDF in a writable folder, up to 1,000 pages within notebook limits. Existing files are preserved.

Opening requires a readable, unprotected PDF up to 32 MiB and 10,000 pages. Bytes and page images stay in memory until close or credential revocation. Reopening can restore position and zoom. Credential-backed checkpoints are encrypted, and passwordless private checkpoints stay in memory. See [reader state and history clearing](../../../development/architecture/reader-state.md).

In fullscreen, hold the page for about 400 ms and drag to move the magnifier. While holding, tap **+** or **−** with another finger. Zoom ranges from 150% to 300%, shared with comics under **Settings → Books & Comics → Comic & PDF magnifier zoom**.

## Document contents

Use **Pages & search → Document contents** for embedded bookmarks. Tap the title to jump or the chevron to expand.

## Search

Use **Pages & search → Find in PDF**. Search requires a text layer and matches literal text without case. **Next match** and **Previous match** wrap. Limits are 256 query characters, 1,000 results and 8 MiB of extracted text.

## Background beside side controls

On iOS, **Reduce Transparency** disables the decorative page background beneath side controls.

## Page-turn motion

**High Contrast / E Ink** or system reduced motion disables the page-turn slide.

## External display

Connect a display or use system screen sharing for picture-only output. Protected-session gates and app inactivity blank the dedicated output.

## Internal page links

Tap a link with a finger. **Undo page jump** is available for three seconds.
