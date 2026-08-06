"""Searchable PDF text-layer inspection and rewriting."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import time
from typing import Any

from .config import ExtractConfig, RewritePolicy
from .models import OcrLine
from .surya_pipeline import normalize_surya_markup

try:
    import fitz
except ImportError:  # pragma: no cover - only needed for PDF rewriting.
    fitz = None


FULL_PAGE_IMAGE_THRESHOLD = 0.80
HIGH_IMAGE_COVERAGE_THRESHOLD = 0.65
MIN_TEXT_CHARS = 8


def log_progress(step: str, message: str) -> None:
    """Print a concise, immediately visible progress update."""

    print(f"[{step}] {message}", flush=True)


def progress_interval(total: int) -> int:
    """Report about every 5%, but never more often than every 25 pages."""

    return max(25, math.ceil(total / 20))


def should_report_progress(completed: int, total: int) -> bool:
    """Return whether a sparse page-progress update is due."""

    return completed == total or completed % progress_interval(total) == 0


@dataclass(frozen=True)
class PageClassification:
    """PDF object-structure classification for one page."""

    page_index: int
    class_name: str
    action: str
    visible_text_chars: int
    hidden_text_chars: int
    image_coverage: float
    full_page_image: bool
    drawing_count: int
    page_width: float
    page_height: float
    rotation: int
    hidden_text_bboxes: list[tuple[float, float, float, float]]


@dataclass(frozen=True)
class RewriteSummary:
    """Counts and output location for an OCR PDF rewrite run."""

    output_pdf: str
    page_actions: dict[str, int]
    page_classes: dict[str, int]


def require_fitz() -> Any:
    """Return PyMuPDF or fail only when PDF rewriting is requested."""

    if fitz is None:
        raise RuntimeError("PyMuPDF is required for OCR PDF rewriting.")
    return fitz


def rect_area(rect: Any) -> float:
    """Return a non-negative rectangle area."""

    width = max(0.0, float(rect.x1) - float(rect.x0))
    height = max(0.0, float(rect.y1) - float(rect.y0))
    return width * height


def trace_chars(span: dict[str, Any]) -> str:
    """Extract Unicode text from one PyMuPDF texttrace span."""

    chars: list[str] = []
    for char in span.get("chars", []):
        if not char:
            continue
        codepoint = char[0]
        if isinstance(codepoint, int) and codepoint > 0:
            chars.append(chr(codepoint))
    return "".join(chars)


class PdfPageClassifier:
    """Classify PDF pages by object structure for OCR PDF rewriting."""

    def __init__(self, doc: Any) -> None:
        self.fitz = require_fitz()
        self.doc = doc

    def classify_all(self, policy: RewritePolicy) -> list[PageClassification]:
        return [self.classify_page(page_index, policy) for page_index in range(len(self.doc))]

    def classify_page(self, page_index: int, policy: RewritePolicy) -> PageClassification:
        page = self.doc[page_index]
        page_rect = page.rect
        page_area = max(rect_area(page_rect), 1.0)
        visible_chars, hidden_chars, hidden_bboxes = self.inspect_text(page)
        image_coverage, full_page_image = self.inspect_images(page, page_area)
        drawing_count = len(page.get_drawings())

        if policy == RewritePolicy.RASTERIZE:
            class_name = "forced-rasterize"
            action = "rasterize"
        elif policy == RewritePolicy.REPLACE_HIDDEN:
            class_name = "forced-replace-hidden"
            action = "replace-hidden"
        elif policy == RewritePolicy.PRESERVE:
            class_name = "forced-preserve"
            action = "preserve"
        else:
            class_name, action = self.auto_classification(
                visible_chars=visible_chars,
                hidden_chars=hidden_chars,
                image_coverage=image_coverage,
                full_page_image=full_page_image,
            )

        return PageClassification(
            page_index=page_index,
            class_name=class_name,
            action=action,
            visible_text_chars=visible_chars,
            hidden_text_chars=hidden_chars,
            image_coverage=round(image_coverage, 4),
            full_page_image=full_page_image,
            drawing_count=drawing_count,
            page_width=float(page_rect.width),
            page_height=float(page_rect.height),
            rotation=int(page.rotation),
            hidden_text_bboxes=hidden_bboxes,
        )

    @staticmethod
    def auto_classification(
        visible_chars: int,
        hidden_chars: int,
        image_coverage: float,
        full_page_image: bool,
    ) -> tuple[str, str]:
        """Choose a conservative rewrite action from page structure."""

        has_visible_text = visible_chars >= MIN_TEXT_CHARS
        has_hidden_text = hidden_chars >= MIN_TEXT_CHARS
        image_dominant = full_page_image or image_coverage >= HIGH_IMAGE_COVERAGE_THRESHOLD

        if image_dominant and not has_hidden_text:
            return "scanned-no-ocr", "add-hidden-text"
        if image_dominant and has_hidden_text:
            return "scanned-hidden-ocr", "replace-hidden"
        if has_visible_text and not image_dominant:
            return "born-digital", "rasterize"
        return "uncertain", "rasterize"

    def inspect_text(self, page: Any) -> tuple[int, int, list[tuple[float, float, float, float]]]:
        visible_chars = 0
        hidden_chars = 0
        hidden_bboxes: list[tuple[float, float, float, float]] = []

        for span in page.get_texttrace():
            text = trace_chars(span)
            char_count = len("".join(text.split()))
            if char_count == 0:
                continue

            render_mode = span.get("type")
            opacity = float(span.get("opacity", 1.0) or 0.0)
            is_hidden = render_mode == 3 or opacity == 0.0
            if is_hidden:
                hidden_chars += char_count
                bbox = span.get("bbox")
                if bbox:
                    hidden_bboxes.append(tuple(float(value) for value in bbox))
            else:
                visible_chars += char_count

        return visible_chars, hidden_chars, hidden_bboxes

    def inspect_images(self, page: Any, page_area: float) -> tuple[float, bool]:
        image_area = 0.0
        full_page_image = False
        blocks = page.get_text("dict").get("blocks", [])

        for block in blocks:
            if block.get("type") != 1:
                continue
            image_rect = self.fitz.Rect(block.get("bbox", page.rect))
            image_rect = image_rect & page.rect
            coverage = rect_area(image_rect) / page_area
            image_area += rect_area(image_rect)
            if coverage >= FULL_PAGE_IMAGE_THRESHOLD:
                full_page_image = True

        return min(image_area / page_area, 1.0), full_page_image


class FullPageSuryaPdfRewriter:
    """Create a searchable OCR PDF from full-page Surya predictions."""

    def __init__(
        self,
        input_pdf: Path,
        output_pdf: Path,
        predictions_by_page: dict[int, dict[str, Any]],
        config: ExtractConfig | None = None,
    ) -> None:
        self.fitz = require_fitz()
        self.input_pdf = input_pdf
        self.output_pdf = output_pdf
        self.predictions_by_page = predictions_by_page
        self.config = config or ExtractConfig()

    def rewrite(self, policy: RewritePolicy) -> RewriteSummary:
        started = time.monotonic()
        doc = self.fitz.open(self.input_pdf)
        try:
            log_progress("pdf", f"inspecting {len(doc)} pages for text-layer rewrite")
            classifications = PdfPageClassifier(doc).classify_all(policy=policy)
            target_total = sum(
                classification.page_index in self.predictions_by_page
                for classification in classifications
            )
            log_progress("pdf", f"rewriting {target_total} pages")
            page_actions: dict[str, int] = {}
            page_classes: dict[str, int] = {}
            completed = 0

            for classification in classifications:
                page_classes[classification.class_name] = (
                    page_classes.get(classification.class_name, 0) + 1
                )

                prediction = self.predictions_by_page.get(classification.page_index)
                if prediction is None:
                    continue
                completed += 1
                if classification.action == "preserve":
                    page_actions[classification.action] = (
                        page_actions.get(classification.action, 0) + 1
                    )
                    if should_report_progress(completed, target_total):
                        log_progress("pdf", f"rewritten {completed}/{target_total} pages")
                    continue

                page_actions[classification.action] = (
                    page_actions.get(classification.action, 0) + 1
                )
                self.rewrite_page(doc, classification, prediction)
                if should_report_progress(completed, target_total):
                    log_progress("pdf", f"rewritten {completed}/{target_total} pages")

            log_progress("pdf", f"saving and compressing: {self.output_pdf}")
            doc.save(
                self.output_pdf,
                garbage=4,
                deflate=True,
                deflate_images=True,
                deflate_fonts=True,
                use_objstms=1,
            )
            log_progress(
                "pdf",
                f"save complete in {time.monotonic() - started:.1f}s",
            )
        finally:
            doc.close()

        return RewriteSummary(
            output_pdf=str(self.output_pdf),
            page_actions=page_actions,
            page_classes=page_classes,
        )

    def rewrite_page(self, doc: Any, classification: PageClassification, prediction: dict[str, Any]) -> None:
        page_index = classification.page_index
        if classification.action == "rasterize":
            page = self.rasterize_page(doc, page_index)
            self.insert_surya_text(page, prediction)
            return

        page = doc[page_index]
        if classification.action == "replace-hidden":
            self.remove_invisible_text(page)
        self.insert_surya_text(page, prediction)

    def remove_invisible_text(self, page: Any) -> None:
        """Remove hidden OCR text without touching images, drawings, or visible text."""

        page.add_redact_annot(page.rect, fill=None, cross_out=False)
        page.apply_redactions(
            images=self.fitz.PDF_REDACT_IMAGE_NONE,
            graphics=self.fitz.PDF_REDACT_LINE_ART_NONE,
            text=self.fitz.PDF_REDACT_TEXT_REMOVE_INVISIBLE,
        )

    def rasterize_page(self, doc: Any, page_index: int) -> Any:
        """Replace one page with a raster image of its visual content."""

        page = doc[page_index]
        rect = page.rect
        pixmap = page.get_pixmap(
            dpi=self.config.rewrite.raster_dpi,
            colorspace=self.fitz.csGRAY,
            alpha=False,
            annots=True,
        )
        image_stream = pixmap.tobytes(
            "jpeg",
            jpg_quality=self.config.rewrite.raster_jpeg_quality,
        )

        doc.delete_page(page_index)
        page = doc.new_page(pno=page_index, width=rect.width, height=rect.height)
        page.insert_image(page.rect, stream=image_stream, keep_proportion=False)
        return page

    def insert_surya_text(self, page: Any, prediction: dict[str, Any]) -> None:
        """Insert Surya text lines as invisible searchable text."""

        image_bbox = prediction.get("image_bbox")
        if not image_bbox or len(image_bbox) != 4:
            image_bbox = [0.0, 0.0, page.rect.width, page.rect.height]

        for line in prediction.get("text_lines", []):
            text = normalize_surya_markup(line.get("text", ""))
            bbox = line.get("bbox")
            if not text or not bbox or len(bbox) != 4:
                continue
            rect = self.map_surya_bbox_to_page(page, bbox, image_bbox)
            if rect.is_empty or rect.is_infinite:
                continue

            self.insert_hidden_text(page, rect, text)

    def insert_hidden_text(self, page: Any, rect: Any, text: str) -> None:
        """Insert one or more invisible lines, shrinking long LaTeX to fit."""

        hidden_lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not hidden_lines:
            return

        base_font_size = max(
            self.config.rewrite.min_font_size,
            min(self.config.rewrite.max_font_size, rect.height * 0.80),
        )
        y = max(page.rect.y0 + base_font_size, rect.y0 + base_font_size)

        for hidden_line in hidden_lines:
            available_width = rect.width
            font_size = self.fit_hidden_font_size(
                hidden_line,
                base_font_size,
                available_width,
            )
            point = self.fitz.Point(rect.x0, min(y, page.rect.y1 - self.config.rewrite.page_margin))
            self.insert_hidden_line(page, point, hidden_line, font_size)
            y += max(font_size * 1.25, self.config.rewrite.min_font_size)

    def fit_hidden_font_size(self, text: str, base_font_size: float, available_width: float) -> float:
        """Return a font size that keeps hidden text inside page width."""

        if available_width <= 0:
            return self.config.rewrite.min_font_size

        text_width_at_one_point = self.fitz.get_text_length(
            text,
            fontname="helv",
            fontsize=1.0,
        )
        if text_width_at_one_point <= 0:
            return base_font_size

        fitting_size = available_width / text_width_at_one_point
        return max(
            0.1,
            min(base_font_size, fitting_size),
        )

    def insert_hidden_line(self, page: Any, point: Any, text: str, font_size: float) -> None:
        try:
            page.insert_text(
                point,
                text,
                fontname="helv",
                fontsize=font_size,
                render_mode=3,
                overlay=True,
            )
        except Exception:
            safe_text = text.encode("latin-1", errors="replace").decode("latin-1")
            page.insert_text(
                point,
                safe_text,
                fontname="helv",
                fontsize=font_size,
                render_mode=3,
                overlay=True,
            )

    def map_surya_bbox_to_page(self, page: Any, bbox: list[float], image_bbox: list[float]) -> Any:
        image_x0, image_y0, image_x1, image_y1 = [float(value) for value in image_bbox]
        image_width = max(image_x1 - image_x0, 1.0)
        image_height = max(image_y1 - image_y0, 1.0)
        x0, y0, x1, y1 = [float(value) for value in bbox]

        page_rect = page.rect
        mapped = self.fitz.Rect(
            page_rect.x0 + ((x0 - image_x0) / image_width) * page_rect.width,
            page_rect.y0 + ((y0 - image_y0) / image_height) * page_rect.height,
            page_rect.x0 + ((x1 - image_x0) / image_width) * page_rect.width,
            page_rect.y0 + ((y1 - image_y0) / image_height) * page_rect.height,
        )
        return mapped & page_rect


class OcrLinePdfRewriter(FullPageSuryaPdfRewriter):
    """Create a searchable OCR PDF from page-coordinate OcrLine records."""

    def __init__(
        self,
        input_pdf: Path,
        output_pdf: Path,
        lines: list[OcrLine],
        config: ExtractConfig | None = None,
    ) -> None:
        super().__init__(
            input_pdf=input_pdf,
            output_pdf=output_pdf,
            predictions_by_page={},
            config=config,
        )
        self.lines_by_page: dict[int, list[OcrLine]] = {}
        for line in lines:
            self.lines_by_page.setdefault(line.page.page_no - 1, []).append(line)

    def rewrite(self, policy: RewritePolicy) -> RewriteSummary:
        started = time.monotonic()
        doc = self.fitz.open(self.input_pdf)
        try:
            log_progress("pdf", f"inspecting {len(doc)} pages for text-layer rewrite")
            classifications = PdfPageClassifier(doc).classify_all(policy=policy)
            target_total = sum(
                classification.page_index in self.lines_by_page
                for classification in classifications
            )
            log_progress("pdf", f"rewriting {target_total} pages")
            page_actions: dict[str, int] = {}
            page_classes: dict[str, int] = {}
            completed = 0

            for classification in classifications:
                page_classes[classification.class_name] = (
                    page_classes.get(classification.class_name, 0) + 1
                )
                lines = self.lines_by_page.get(classification.page_index)
                if not lines:
                    continue
                completed += 1
                if classification.action == "preserve":
                    page_actions[classification.action] = (
                        page_actions.get(classification.action, 0) + 1
                    )
                    if should_report_progress(completed, target_total):
                        log_progress("pdf", f"rewritten {completed}/{target_total} pages")
                    continue

                page_actions[classification.action] = (
                    page_actions.get(classification.action, 0) + 1
                )
                self.rewrite_line_page(doc, classification, lines)
                if should_report_progress(completed, target_total):
                    log_progress("pdf", f"rewritten {completed}/{target_total} pages")

            log_progress("pdf", f"saving and compressing: {self.output_pdf}")
            doc.save(
                self.output_pdf,
                garbage=4,
                deflate=True,
                deflate_images=True,
                deflate_fonts=True,
                use_objstms=1,
            )
            log_progress(
                "pdf",
                f"save complete in {time.monotonic() - started:.1f}s",
            )
        finally:
            doc.close()

        return RewriteSummary(
            output_pdf=str(self.output_pdf),
            page_actions=page_actions,
            page_classes=page_classes,
        )

    def rewrite_line_page(
        self,
        doc: Any,
        classification: PageClassification,
        lines: list[OcrLine],
    ) -> None:
        page_index = classification.page_index
        if classification.action == "rasterize":
            page = self.rasterize_page(doc, page_index)
        else:
            page = doc[page_index]
            if classification.action == "replace-hidden":
                self.remove_invisible_text(page)

        for line in lines:
            if (
                classification.action != "rasterize"
                and line.metadata.get("source") == "docling_text_cell"
                and not line.metadata.get("from_ocr", False)
            ):
                continue
            if line.bbox is None:
                continue
            rect = self.fitz.Rect(*line.bbox.as_list()) & page.rect
            if rect.is_empty or rect.is_infinite:
                continue
            self.insert_hidden_text(page, rect, line.text)
