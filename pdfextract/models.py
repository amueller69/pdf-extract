"""Shared normalized data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import OutputMode, RewritePolicy, WorkflowMode


@dataclass(frozen=True)
class BBox:
    """Bounding box in page coordinates."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)

    def as_list(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]


@dataclass(frozen=True)
class PageRef:
    """One-based page reference."""

    page_no: int
    width: float | None = None
    height: float | None = None


@dataclass
class OcrLine:
    """Recognized text line with optional geometry."""

    text: str
    page: PageRef
    bbox: BBox | None = None
    source_bbox: BBox | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunRequest:
    """User request after CLI parsing and default resolution."""

    input_pdf: Path
    output_mode: OutputMode
    workflow: WorkflowMode
    markdown_out: Path | None
    pdf_out: Path | None
    rewrite_policy: RewritePolicy
    json_out: Path | None = None
    crops_dir: Path | None = None
    pages: str | None = None
    debug: bool = False
    save_crops: bool = False
    run_surya_math: bool = True


@dataclass
class RunResult:
    """Paths and metadata produced by one workflow run."""

    markdown_out: Path | None = None
    pdf_out: Path | None = None
    json_out: Path | None = None
    debug_out: Path | None = None
    report: dict[str, Any] = field(default_factory=dict)
