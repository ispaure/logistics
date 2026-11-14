# PDF Reader

Open a PDF from a local, remote or unlocked LocalCrypt browser. Scroll, use the page arrows or enter a page number in **Page**. **F11** toggles fullscreen.

To annotate, choose **⋯ → Duplicate as .rmdoc to annotate**. This requires a writable folder and creates a sibling notebook for PDFs up to 1,000 pages within archive limits. Existing files are preserved. Open the copy in [Notebooks](../../notebooks/user/user.md).

PDFs are read-only and limited to 32 MiB. Decrypted bytes stay in memory until close or credential revocation. Encrypted PDFs require decryption elsewhere before opening.

## Search

Use **Find in PDF** or **Ctrl+F** (**⌘F** on macOS). Search matches literal text without case and requires a text layer. **Next match** and **Previous match** wrap. The limits are 256 characters per query, 1,000 results and 8 MiB of extracted text.

## Page-turn motion

Page turns slide within the reading area.

## Reading position and platform differences

Provider-backed locations can restore page and scroll position. Credential-backed positions are encrypted and passwordless private positions stay in memory. See [reader state and history clearing](../../../development/architecture/reader-state.md) and the [mobile guide](../user_mobile/user_mobile.md).

## Internal page links

Follow an internal link, then use **Undo page jump** within three seconds to return.
