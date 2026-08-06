# PDF Extract Functional Requirements

## Core Functional Requirements

- Provide one user-facing command that orchestrates PDF inspection, OCR, text-layer rewriting, and readable text/Markdown extraction.

- Produce reliable searchable PDFs for Zotero.
  The PDF text layer is authoritative because Zotero indexes it into SQLite, and that indexed text is later used by MCP search and embedding workflows. The tool must therefore prioritize textual fidelity in the written text layer, not merely produce visually acceptable OCR.
  - Detect whether the existing text layer is safe to preserve or must be replaced, including visible text, invisible OCR layers, missing text layers, duplicated/malformed layers, and math-hostile born-digital text.
  - When preservation is unsafe, support conservative rasterize-and-rewrite behavior that creates a fresh OCR text layer.
  - When routing block equations and inline math to Surya, normalize the geometric information returned by Surya into the original PDF page coordinate system before using it for text-layer rewriting.
  - Exact highlight geometry is less important than complete searchable/copyable text, but hidden text should still be placed in the correct page region and should not collide with unrelated content when avoidable.

- Produce LLM-readable text or Markdown with clear page boundaries and better document structure than raw PDF text extraction.
  - Separate footnotes from body text, especially in law review and legal-academic PDFs, so footnote quotations and parentheticals are not treated as the author's main argument.
  - Handle multi-column layouts, tables, captions, figures, headers, footers, and reading order better than naive text concatenation.
  - Preserve or improve math readability by routing detected math regions to math-capable OCR where appropriate.

- Route documents or document regions to the appropriate recognition method.
  - Use Docling as the default layout/document model for mixed documents.
  - Use ordinary OCR or existing text extraction for non-math prose where it is sufficient.
  - Use Surya for math-heavy or math-suspect regions where normal extraction/OCR is inadequate.
  - Allow a user override that bypasses Docling and runs full-page Surya OCR for the entire document.

- Keep structured/debug metadata available when useful, but the main outputs must remain practical: searchable PDFs and readable text/Markdown.

## User-Facing Workflow Requirements

- The default workflow should be Docling-first hybrid extraction.
  - Run Docling layout/document conversion.
  - Use Docling reading order and layout structure for the main document flow.
  - Detect display formulas from Docling formula layout clusters.
  - Detect inline math candidates from text spans/items.
  - Route selected math candidates to Surya.
  - Reintegrate Surya-recognized math into Markdown and, when requested, into the searchable PDF text layer.

- The full Surya override should be available as a separate workflow.
  - This should bypass Docling for now.
  - It should preserve the proven behavior of the archived standalone Surya flow.
  - It should produce Markdown and optionally a searchable OCR PDF from full-page Surya output.
  - It should not initially attempt to stitch selected full-Surya pages into an otherwise Docling-generated document.

- The command-line interface should stay simple for normal use.
  - Required input: PDF path.
  - User should be able to request Markdown/text output, OCR PDF output, or both.
  - If Markdown output is not specified, write `<input_stem>_extracted.md` next to the input PDF.
  - If OCR PDF output is not specified, write `<input_stem>_ocr.pdf` next to the input PDF.
  - The tool must never overwrite the input PDF.

- Useful user-facing overrides should include:
  - Force full Surya workflow for the whole document.
  - Force OCR instead of trusting an existing text layer.
  - Force rasterize-and-rewrite behavior for OCR PDF output.
  - Preserve an existing text layer when explicitly requested.
  - Select pages/page ranges for diagnostic or partial runs.

- Low-level tuning should not clutter the normal CLI.
  Batch sizes, DPI, Surya input mode, crop expansion, math threshold, queue size, and related knobs should be configuration defaults. They can remain available as debug/developer options if needed.

## OCR PDF Text-Layer Requirements

- The rewritten OCR text layer must prioritize:
  - Complete text.
  - Correct page association.
  - Correct reading order where practical.
  - Searchable/copyable math text where math OCR is used.

- The tool must support at least these rewrite policies:
  - `auto`: inspect the PDF and choose a conservative action.
  - `rasterize`: rasterize page visuals and write a fresh hidden OCR layer.
  - `replace-hidden`: remove an existing hidden OCR layer and write a fresh one.
  - `preserve`: preserve the existing text layer when the user explicitly requests it.

- The current Surya text-layer rewrite behavior is acceptable as a starting point.
  - Highlight rectangles may be approximate.
  - Long LaTeX strings may need to be shrunk or compressed into their visual region.
  - Copy/paste and indexing fidelity matter more than perfect highlight geometry.

- Math routed through Surya must be reintegrated into the OCR text-layer model.
  - Display/block formulas can use coarse placement inside the corresponding formula-zone bbox.
  - Inline math/text crops need more precise mapping back into the original paragraph or text-line region.
  - Crop-relative Surya bboxes must be translated to original page coordinates before PDF writing.

## Markdown/Text Requirements

- Markdown output should be readable by humans and LLMs.
- Page boundaries should be explicit.
- Docling reading order should be preferred in the hybrid workflow.
- Surya math output should replace or augment the corresponding Docling math/text regions.
- Tables, captions, figures, headers, footers, and footnotes should be represented more usefully than with raw PDF text extraction.
- Known acceptable first-version limitations:
  - PDF front matter may appear as body text.
  - Heading levels may be inferred imperfectly.
  - Dense inline math may still require manual review or full Surya override.

## Debugging Requirements

- Debug output should be available but not written during normal operation.
- When enabled, debug output should make it possible to inspect:
  - Docling layout clusters and labels.
  - Math routing candidates and routing reasons.
  - Original, expanded, crop-relative, and page-mapped bboxes.
  - Saved crop images.
  - Surya input mode and batch timing.
  - OCR PDF rewrite actions by page.
- Debug files should be easy to clean up.

## Implementation Notes

These notes describe the current intended implementation shape. They are not the functional contract.

### Coordinate Reconciliation

All recognized text used by the OCR PDF writer should be normalized into original PDF page coordinates, regardless of source:

- Docling items.
- Full-page Surya lines.
- Surya results from direct image crops.
- Surya results from temporary PDF crop pages.

For every Surya-routed crop, retain enough metadata to map results back to the original page:

- Original PDF page number.
- Original Docling bbox.
- Expanded crop bbox.
- Crop image size.
- Surya input mode.
- Surya line bbox in input/crop coordinates.
- Final mapped bbox in original page coordinates.

Display/block formulas may use coarse placement:

- Insert recognized formula text inside the corresponding Docling formula-zone bbox.
- Exact per-symbol highlight fidelity is not required.

Inline math/text crops need more precise placement:

- Map crop-relative Surya line bboxes back into the original page bbox.
- Preserve useful line-level positioning inside the paragraph/text region.
- Avoid replacing a whole paragraph with a truncated crop result.

### Proposed Package Structure

The prototype should be converted into an installable package with separate components:

- CLI entrypoint: argument parsing, output path defaults, workflow selection.
- Configuration: default DPI, batching, math thresholds, rewrite policy, debug settings.
- Docling workflow: conversion, backend lifetime, layout/debug extraction.
- Math routing: formula-zone detection, text-item scoring, crop planning.
- Crop rendering: Docling page crop rendering and temp PDF crop preparation.
- Surya runtime: model session, batching, GPU cleanup, OOM recovery.
- Full-page Surya workflow: standalone full-document OCR path.
- Output model: normalized pages/items/lines with page-coordinate bboxes.
- Markdown writer: hybrid Markdown assembly.
- OCR PDF writer: text-layer inspection and rewrite.
- Debug writer: JSON, crop images, routing traces.

Surya should have shared runtime code for both use cases:

- Docling hybrid crop recognition.
- Full-page Surya override.

Avoid over-engineering with deep inheritance. Prefer small classes/dataclasses with clear inputs and outputs.
