# PDF reader development

The PDF feature adapts bounded document access and rendering to desktop and
mobile readers. Navigation, search and annotation-copy creation sit above that
read-only document boundary.

See the [desktop guide](../user/user.md) and [mobile guide](../user_mobile/user_mobile.md) for reader controls.

## Follow an internal page link

Click an internal link in a disposable PDF.
`Python/features/pdf/ui/reader.py:PDFWindow.offer_link_return` offers a short
return to the previous page; an explicit navigation clears it. The linked-PDF
fixtures exercise the real click path and return behavior:

```sh
python3 dev.py test desktop --exact-file Python/tests/readers/test_pdf_links.py
```

## Open or render a PDF

`document.py:PDFDocument` bounds input to 32 MiB and 10,000 pages. Native backends use QtPdf, PDFKit or Android PdfRenderer with a 2048-pixel raster edge cap. Locked and unsupported PDFs fail during open. Android closes either the transferred renderer or the untransferred descriptor on failure. Private reader sessions clear pixels on suspension and release bytes on close or revocation. Update `mobile_sources.json` for new portable/mobile imports.

## Continuous pages

Desktop `ui/continuous.py:ContinuousPDFView` and mobile `mobile/continuous.py:PDFScroll` rasterize around the viewport. Mobile rejects stale work and evicts distant pixels. Observed scroll updates controls without seeking. Checkpoints support within-page offsets and older page-only records. Paged mobile layout is in `mobile/canvas.py`. See [reader state](../../../development/architecture/reader-state.md).

```sh
python3 dev.py test desktop --exact-file Python/tests/readers/test_pdf_reader.py
python3 dev.py test mobile --exact-file mobile_build/tests/reading/test_pdf_scroll.py
```

Use the managed `pdf_probe.py` for native raster and viewport acceptance.

## Links, search and annotation

- `links.py` normalizes crop and rotation for up to 2,000 links per page. `contents.py` resolves bounded outline destinations to zero-based indices.
- `search.py` matches literal case-insensitive text after whitespace normalization. Image-only pages need an OCR layer. Limits are 256 query characters, 1,000 matches, 10,000 pages and 8 MiB extracted text. `search_controller.py` retains worker ownership through cancellation and rejects stale results. Check `test_pdf_search_controller.py`.
- `annotation.py:duplicate_pdf()` revision-checks the source, embeds its bytes in a sibling RMDOC and publishes create-only with provider privacy intact. Check `test_pdf_annotation.py` for collisions and round trips. Use the managed `pdf-annotation` probe for native menu, ink and reopen.
