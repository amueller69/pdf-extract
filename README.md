# PDF Extract

Hybrid PDF extraction and OCR tooling for producing:

- readable Markdown;
- searchable OCR PDFs;
- structured JSON/debug metadata with layout geometry.

The main goal is text fidelity for search, copy/paste, Zotero indexing, MCP search, and downstream embedding workflows. Perfect visual highlight alignment in rewritten PDFs is useful, but it is secondary to complete and correctly ordered searchable text.

## Current Status

This project now has an installable package in `pdfextract/`.

Working package paths:

- Docling-first hybrid Markdown extraction.
- Docling math routing.
- Docling crop rendering with `page.get_image()`.
- Surya recognition for Docling-routed math crops.
- Hybrid Markdown replacement using Surya math output.
- Full-page Surya override.
- Full-page Surya searchable PDF rewrite.
- Docling hybrid searchable PDF rewrite using normalized page-coordinate OCR lines.

Still expected to evolve:

- better document-type-specific Markdown cleanup, especially for CV/resume layouts;
- more robust geometry validation for crop-to-page mapping;
- richer debug reports;
- more regression testing against the test PDF set;
- editable install into the active venv as the normal usage mode.

## Workflows

### Default: Docling Hybrid

The default workflow is Docling-first.

It does this:

1. Runs Docling PDF layout/document conversion.
2. Enables Docling OCR in non-forced mode so image-only/scanned pages are OCRed while existing PDF text remains available.
3. Uses Docling reading order and layout structure for the main document flow.
4. Detects math candidates from:
   - Docling internal formula layout clusters;
   - text items that score as math-like.
5. Renders only those selected regions as crops.
6. Runs Surya on those crops.
7. Replaces Docling math regions with Surya-recognized math in Markdown.
8. When requested, writes a searchable OCR PDF from normalized page-coordinate text lines.

This is intended for mixed documents with prose, layout structure, and occasional math.

### Full Surya Override

Use `--force-surya` when you want to bypass Docling and OCR full pages with Surya.

This is useful when:

- Docling layout detection is not helping;
- the document is mostly raster/scan content;
- math is dense enough that full-page Surya is simpler;
- you want behavior close to the archived standalone Surya script.

The full Surya path is separate from the Docling hybrid path. It does not currently stitch selected full-Surya pages into a Docling-generated document.

## CLI

Run from the project root for now:

```bash
python -m pdfextract.cli input.pdf
```

After editable install, the intended command is:

```bash
pdf-extract input.pdf
```

### Default Output

```bash
pdf-extract input.pdf
```

Writes Markdown only:

```text
input_extracted.md
```

### Markdown Plus Searchable PDF

```bash
pdf-extract input.pdf --ocr-pdf
```

Writes:

```text
input_extracted.md
input_ocr.pdf
```

This is expected to be the common command.

### Searchable PDF Only

```bash
pdf-extract input.pdf --ocr-pdf --no-markdown
```

Writes:

```text
input_ocr.pdf
```

### Explicit Output Paths

```bash
pdf-extract input.pdf --markdown-out out.md
pdf-extract input.pdf --ocr-pdf --pdf-out out.pdf
pdf-extract input.pdf --ocr-pdf --markdown-out out.md --pdf-out out.pdf
```

The tool must never overwrite the input PDF.

### Full Surya Override

```bash
pdf-extract input.pdf --force-surya
pdf-extract input.pdf --force-surya --ocr-pdf
pdf-extract input.pdf --force-surya --ocr-pdf --no-markdown
```

### Page Selection

```bash
pdf-extract input.pdf --pages 2
pdf-extract input.pdf --pages 2-4
pdf-extract input.pdf --force-surya --pages 1,3-5
```

Docling currently accepts single pages or simple ranges. Full Surya accepts comma-separated pages/ranges.

### Debug Output

```bash
pdf-extract input.pdf --debug --json-out debug.json
```

When `--debug` is set and `--json-out` is not provided, JSON defaults to:

```text
input_extracted.json
```

Save routed math crops:

```bash
pdf-extract input.pdf --debug --save-crops
```

Default crop directory:

```text
input_crops/
```

Override crop directory:

```bash
pdf-extract input.pdf --debug --save-crops --crops-dir /tmp/crops
```

### Disable Surya Math Crops

```bash
pdf-extract input.pdf --no-surya-math
```

This keeps Docling routing/crop metadata available but does not invoke Surya for math crops.

## Output Files

### Markdown

Markdown output is intended to be readable by humans and LLMs.

The Docling hybrid path tries to preserve:

- section structure;
- page boundaries;
- reading order;
- tables;
- list items;
- captions/figures where Docling exposes them;
- Surya-recognized math for routed math regions.

Known limitation: raw Docling Markdown can be rough for highly styled CV/resume layouts. The layout model may identify sections and tables, but the text serializer can still produce spacing artifacts.

### JSON

JSON output can include:

- source path;
- page range;
- Docling status/errors/confidence;
- page/item summaries;
- item labels;
- provenance bboxes;
- table cell geometry;
- math routing candidates;
- crop metadata;
- Surya output for routed crops;
- Docling internal layout clusters when debug is enabled;
- OCR PDF rewrite summary when a PDF is written.

For hybrid math candidates, useful fields include:

- `candidate_id`;
- `page`;
- `reason`;
- `bbox`;
- `bbox_top_left`;
- `crop_bbox`;
- `crop_bbox_top_left`;
- `crop_size_px`;
- `covered_self_refs`;
- `surya_input_mode`;
- `surya`.

### Searchable OCR PDF

The OCR PDF rewrite writes invisible text for search/copy/indexing.

The text layer is authoritative for Zotero indexing. The rewrite prioritizes:

- complete text;
- correct page association;
- practical reading order;
- searchable/copyable math text.

Highlight geometry may be approximate, especially for LaTeX formulas whose textual representation is much longer than the visible formula.

## OCR PDF Rewrite Policies

The CLI exposes:

```bash
--rewrite-policy auto
--rewrite-policy rasterize
--rewrite-policy replace-hidden
--rewrite-policy preserve
```

Current behavior:

- `auto`: inspect page structure and choose a conservative action.
- `rasterize`: rasterize page visuals and write a fresh hidden text layer.
- `replace-hidden`: remove invisible OCR text and write a fresh one.
- `preserve`: leave existing text layer alone for pages being rewritten.

For born-digital pages, `auto` currently tends to rasterize before writing the hidden OCR layer. This is conservative for replacing bad/malformed/math-hostile text layers, but it increases output PDF size.

## Math Handling

Docling can classify layout regions as formulas, but inline math often remains ordinary text. The hybrid workflow handles both:

- display/block formulas: detected from Docling internal formula layout clusters;
- inline/math-heavy text: detected with `pdfextract.math_score.mathematics_score()`.

Display formulas are merged into formula zones before cropping. This avoids the earlier problem where final Docling formula item boxes were fragmented and produced bad crops.

Surya crop recognition uses two modes:

- inline/text crops: direct image input;
- formula zones: crop embedded into normal US-letter temporary PDF pages.

The temp-PDF workaround is intentional. It produced better recognition for clean display-formula crops than passing those formula crops directly as small images.

## Coordinate Handling

The default hybrid workflow has to reconcile Docling and Surya coordinate systems.

Current approach:

- Docling item bboxes are normalized into page coordinates.
- Inline Surya crop bboxes are mapped from crop image coordinates back into the expanded Docling crop bbox.
- Display formula Surya output is placed coarsely inside the Docling formula-zone bbox.
- OCR PDF writing consumes `OcrLine` records whose bboxes are already in original page coordinates.

This is intentionally conservative:

- inline math/text gets more precise placement;
- block formulas get coarse but page-correct placement;
- text search/copy fidelity is prioritized over perfect visual highlight fidelity.

## Package Layout

Current source layout:

```text
pdfextract/
  __init__.py
  cli.py
  config.py
  docling_pipeline.py
  math_score.py
  models.py
  pdf_rewrite.py
  surya_pipeline.py
```

### `cli.py`

Argument parsing, output path defaults, request validation, and workflow selection.

### `config.py`

Central defaults:

- Docling device/batching/crop DPI/math thresholds;
- Surya batching/runtime settings;
- PDF rewrite settings.

Most low-level knobs live here instead of cluttering the CLI.

### `models.py`

Shared lightweight data structures:

- `BBox`;
- `PageRef`;
- `OcrLine`;
- `RunRequest`;
- `RunResult`.

These are used to keep coordinate handling consistent across modules.

### `docling_pipeline.py`

Docling-first hybrid workflow:

- conversion;
- route planning;
- formula-zone merging;
- crop rendering;
- Surya crop invocation;
- hybrid Markdown assembly;
- normalized OCR-line generation;
- default OCR PDF rewrite call.

### `surya_pipeline.py`

Shared Surya code:

- environment defaults;
- GPU cleanup;
- model session lifecycle;
- crop recognition;
- full-page recognition;
- Surya markup normalization;
- full-page Markdown/JSON workflow.

### `pdf_rewrite.py`

Searchable PDF writing:

- PDF page classification;
- existing text-layer inspection;
- rasterize/replace/preserve policy handling;
- full-page Surya prediction rewriting;
- normalized `OcrLine` rewriting for the Docling hybrid path.

## Environment Notes

This has been developed in WSL2 with ROCm-backed PyTorch exposed through the CUDA path.

GPU use is expected. The code intentionally avoids silent CPU fallback for Docling/Surya-heavy operations because CPU fallback can look like a hang.

Surya environment defaults are conservative for a 12 GB GPU:

- `DETECTOR_BATCH_SIZE=16`;
- `RECOGNITION_BATCH_SIZE=128`;
- `TORCH_DEVICE=cuda`;
- `MIOPEN_FIND_MODE=FAST`;
- `PYTORCH_TUNABLEOP_ENABLED=0`.

## Example Commands

Docling hybrid Markdown:

```bash
python -m pdfextract.cli test-docs/ocr-math-test.pdf
```

Docling hybrid Markdown plus searchable PDF:

```bash
python -m pdfextract.cli test-docs/ocr-math-test.pdf --ocr-pdf
```

Docling hybrid debug run with crops:

```bash
python -m pdfextract.cli test-docs/ocr-math-test.pdf \
  --pages 2 \
  --debug \
  --save-crops \
  --json-out /tmp/hybrid-p2.json \
  --markdown-out /tmp/hybrid-p2.md
```

Full-page Surya override:

```bash
python -m pdfextract.cli test-docs/ocr-math-test.pdf \
  --force-surya \
  --pages 2 \
  --markdown-out /tmp/surya-p2.md \
  --json-out /tmp/surya-p2.json
```

Full-page Surya searchable PDF:

```bash
python -m pdfextract.cli test-docs/ocr-math-test.pdf \
  --force-surya \
  --ocr-pdf \
  --pages 2 \
  --markdown-out /tmp/surya-p2.md \
  --pdf-out /tmp/surya-p2.pdf
```

OCR PDF only:

```bash
python -m pdfextract.cli test-docs/ocr-math-test.pdf \
  --ocr-pdf \
  --no-markdown
```

## Known Limitations

- CV/resume Markdown can contain spacing and alignment artifacts.
- Docling-derived heading levels may be imperfect.
- PDF front matter can appear as body text.
- Full-page Surya can still make math mistakes in inline expressions.
- Hybrid formula-zone OCR placement in the PDF text layer is coarse.
- Highlight rectangles in rewritten PDFs are approximate.
- Page-level full-Surya stitch-in to a Docling document is not implemented.
- OCR PDF rewrite for selected pages preserves the original PDF page count and rewrites only pages for which OCR output exists.

## Legacy Archive

The earlier probes, standalone scripts, reports, and generated debug artifacts were moved outside the active project to:

```text
/home/alex/Repos/pdf-extract-archive/legacy-2026-06-18/
```

They remain available as implementation references without cluttering the installable project.
