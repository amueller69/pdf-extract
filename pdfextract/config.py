"""Configuration defaults for PDF extraction workflows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class WorkflowMode(str, Enum):
    """Top-level extraction workflow."""

    DOCLING_HYBRID = "docling-hybrid"
    SURYA_FULL = "surya-full"


class RewritePolicy(str, Enum):
    """OCR PDF text-layer rewrite policy."""

    AUTO = "auto"
    RASTERIZE = "rasterize"
    REPLACE_HIDDEN = "replace-hidden"
    PRESERVE = "preserve"


class OutputMode(str, Enum):
    """Requested user-facing outputs."""

    MARKDOWN = "markdown"
    OCR_PDF = "ocr-pdf"
    BOTH = "both"


@dataclass(frozen=True)
class DoclingDefaults:
    """Docling conversion and routing defaults."""

    device: str = "cuda"
    threads: int = 4
    layout_batch_size: int = 1
    ocr_batch_size: int = 1
    table_batch_size: int = 1
    queue_max_size: int = 4
    math_threshold: float = 0.70
    formula_zone_gap: float = 18.0
    crop_expansion: float = 0.08
    crop_detection_dpi: int = 96
    crop_recognition_dpi: int = 300
    crop_pdf_dpi: int = 300
    do_ocr: bool = True
    do_tables: bool = True
    do_formulas: bool = False
    ocr_lang: tuple[str, ...] = ("eng",)
    force_full_page_ocr: bool = False


@dataclass(frozen=True)
class SuryaDefaults:
    """Surya runtime and batching defaults."""

    enabled_for_math_crops: bool = True
    detector_batch_size: int = 16
    recognition_batch_size: int = 128
    crop_batch_size: int = 8
    page_chunk_size: int = 2
    math_mode: bool = True
    torch_device: str = "cuda"
    miopen_find_mode: str = "FAST"
    pytorch_tunableop_enabled: str = "0"


@dataclass(frozen=True)
class RewriteDefaults:
    """Text-layer rewrite defaults."""

    policy: RewritePolicy = RewritePolicy.AUTO
    raster_dpi: int = 400
    raster_jpeg_quality: int = 92
    min_font_size: float = 0.5
    max_font_size: float = 20.0
    page_margin: float = 6.0


@dataclass(frozen=True)
class ExtractConfig:
    """Top-level immutable configuration for one run."""

    docling: DoclingDefaults = DoclingDefaults()
    surya: SuryaDefaults = SuryaDefaults()
    rewrite: RewriteDefaults = RewriteDefaults()
