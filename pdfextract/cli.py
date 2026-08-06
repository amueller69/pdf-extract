"""Command-line entrypoint for pdf-extract."""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import OutputMode, RewritePolicy, WorkflowMode
from .models import RunRequest


def default_markdown_path(input_pdf: Path) -> Path:
    return input_pdf.with_name(f"{input_pdf.stem}_extracted.md")


def default_ocr_pdf_path(input_pdf: Path) -> Path:
    return input_pdf.with_name(f"{input_pdf.stem}_ocr.pdf")


def default_json_path(input_pdf: Path) -> Path:
    return input_pdf.with_name(f"{input_pdf.stem}_extracted.json")


def default_crops_dir(input_pdf: Path) -> Path:
    return input_pdf.with_name(f"{input_pdf.stem}_crops")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf-extract",
        description="Extract readable Markdown and/or write searchable OCR PDFs.",
    )
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument(
        "--ocr-pdf",
        action="store_true",
        help="Also write a searchable OCR PDF.",
    )
    parser.add_argument(
        "--no-markdown",
        action="store_true",
        help="Do not write Markdown output.",
    )
    parser.add_argument("--markdown-out", type=Path)
    parser.add_argument("--pdf-out", type=Path)
    parser.add_argument("--json-out", type=Path, help="Optional structure/debug JSON output path.")
    parser.add_argument("--save-crops", action="store_true", help="Save routed math crop PNGs for debugging.")
    parser.add_argument("--crops-dir", type=Path, help="Directory for saved debug crop PNGs.")
    parser.add_argument(
        "--no-surya-math",
        dest="run_surya_math",
        action="store_false",
        help="Do not run Surya on Docling-routed math crops.",
    )
    parser.add_argument(
        "--force-surya",
        action="store_true",
        help="Bypass Docling and run full-page Surya OCR for the whole document.",
    )
    parser.add_argument(
        "--rewrite-policy",
        choices=[item.value for item in RewritePolicy],
        default=RewritePolicy.AUTO.value,
    )
    parser.add_argument("--pages", help="Optional one-based page/range selection.")
    parser.add_argument("--debug", action="store_true")
    return parser


def request_from_args(args: argparse.Namespace) -> RunRequest:
    input_pdf = args.input_pdf.expanduser().resolve()
    output_mode = output_mode_from_args(args)
    markdown_out = args.markdown_out
    pdf_out = args.pdf_out
    json_out = args.json_out

    if output_mode in {OutputMode.MARKDOWN, OutputMode.BOTH} and markdown_out is None:
        markdown_out = default_markdown_path(input_pdf)
    if output_mode in {OutputMode.OCR_PDF, OutputMode.BOTH} and pdf_out is None:
        pdf_out = default_ocr_pdf_path(input_pdf)

    workflow = WorkflowMode.SURYA_FULL if args.force_surya else WorkflowMode.DOCLING_HYBRID
    return RunRequest(
        input_pdf=input_pdf,
        output_mode=output_mode,
        workflow=workflow,
        markdown_out=markdown_out,
        pdf_out=pdf_out,
        json_out=json_out or (default_json_path(input_pdf) if args.debug else None),
        crops_dir=args.crops_dir or (default_crops_dir(input_pdf) if args.save_crops else None),
        rewrite_policy=RewritePolicy(args.rewrite_policy),
        pages=args.pages,
        debug=args.debug,
        save_crops=args.save_crops,
        run_surya_math=args.run_surya_math,
    )


def validate_request(request: RunRequest) -> None:
    if not request.input_pdf.exists():
        raise FileNotFoundError(f"Input PDF does not exist: {request.input_pdf}")
    if not request.input_pdf.is_file():
        raise ValueError(f"Input path is not a file: {request.input_pdf}")
    if request.input_pdf.suffix.lower() != ".pdf":
        raise ValueError(f"Input file does not look like a PDF: {request.input_pdf}")
    if request.pdf_out and request.pdf_out.resolve() == request.input_pdf:
        raise ValueError("OCR PDF output must not overwrite the input PDF")
    if request.output_mode is OutputMode.OCR_PDF and request.markdown_out is not None:
        raise ValueError("--markdown-out cannot be used with --no-markdown")


def output_mode_from_args(args: argparse.Namespace) -> OutputMode:
    """Derive the internal output mode from user-facing flags."""

    if args.no_markdown and not args.ocr_pdf:
        raise ValueError("--no-markdown requires --ocr-pdf")
    if args.no_markdown:
        return OutputMode.OCR_PDF
    if args.ocr_pdf:
        return OutputMode.BOTH
    return OutputMode.MARKDOWN


def run(request: RunRequest) -> int:
    validate_request(request)
    if request.workflow is WorkflowMode.SURYA_FULL:
        from .surya_pipeline import SuryaFullPagePipeline

        SuryaFullPagePipeline().run(request)
    else:
        from .docling_pipeline import DoclingHybridPipeline

        DoclingHybridPipeline().run(request)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        request = request_from_args(args)
        return run(request)
    except ValueError as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
