"""Docling-first hybrid extraction pipeline."""

from __future__ import annotations

import gc
import json
import sys
import time
from pathlib import Path
from typing import Any

try:
    import torch
except Exception:  # pragma: no cover - depends on runtime environment.
    torch = None

from docling.datamodel.accelerator_options import (
    AcceleratorDevice,
    AcceleratorOptions,
)
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableFormerMode,
    TableStructureOptions,
    TesseractCliOcrOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
from docling_core.types.doc import (
    BoundingBox,
    DocItemLabel,
    PictureItem,
    TableItem,
    TextItem,
)

from .config import ExtractConfig, OutputMode
from .math_score import mathematics_score
from .models import BBox, OcrLine, PageRef, RunRequest, RunResult


class KeepBackendPdfPipeline(StandardPdfPipeline):
    """Keep page backends alive for later crop rendering."""

    def _init_models(self) -> None:
        super()._init_models()
        self.keep_backend = True

    def _unload(self, conv_res: Any) -> None:
        pass


def log_progress(step: str, message: str) -> None:
    """Print a concise, immediately visible progress update."""

    print(f"[{step}] {message}", flush=True)


def enum_value(value: Any) -> Any:
    """Return enum.value when present, otherwise the original value."""

    return getattr(value, "value", value)


def parse_page_range(value: str | None) -> tuple[int, int]:
    """Parse a one-based page or page range for Docling."""

    if not value:
        return (1, sys.maxsize)

    if "-" in value:
        start, end = value.split("-", 1)
        page_range = (int(start), int(end))
    else:
        page = int(value)
        page_range = (page, page)

    if page_range[0] < 1 or page_range[1] < page_range[0]:
        raise ValueError("pages must be like 1, 3, or 3-8")
    return page_range


def bbox_to_list(obj: Any) -> list[float] | None:
    """Convert Docling bbox-like objects to JSON-safe lists."""

    if obj is None:
        return None
    if hasattr(obj, "as_tuple"):
        return [float(value) for value in obj.as_tuple()]
    if all(hasattr(obj, attr) for attr in ("l", "t", "r", "b")):
        return [float(obj.l), float(obj.t), float(obj.r), float(obj.b)]
    return None


def bbox_from_obj(obj: Any) -> BBox | None:
    """Convert Docling bbox-like objects to the shared BBox model."""

    values = bbox_to_list(obj)
    if values is None:
        return None
    return BBox(values[0], values[1], values[2], values[3])


def bbox_list_from_model(bbox: BBox | None) -> list[float] | None:
    """Convert shared BBox models to JSON-safe lists."""

    return bbox.as_list() if bbox is not None else None


def bbox_origin(obj: Any) -> str | None:
    """Return a bbox coordinate-origin label when available."""

    origin = getattr(obj, "coord_origin", None)
    return str(enum_value(origin)) if origin is not None else None


def bbox_to_top_left_list(obj: Any, page_height: float | None) -> list[float] | None:
    """Convert Docling bbox to top-left origin when the API supports it."""

    if obj is None:
        return None
    if page_height is not None and hasattr(obj, "to_top_left_origin"):
        return bbox_to_list(obj.to_top_left_origin(page_height=page_height))
    return bbox_to_list(obj)


def bbox_to_top_left(obj: Any, page_height: float | None) -> BBox | None:
    """Convert Docling bbox to shared BBox with top-left origin."""

    if obj is None:
        return None
    if page_height is not None and hasattr(obj, "to_top_left_origin"):
        return bbox_from_obj(obj.to_top_left_origin(page_height=page_height))
    return bbox_from_obj(obj)


def text_cell_bbox_to_top_left(cell: Any, page_height: float) -> BBox | None:
    """Convert a Docling text cell rectangle to a top-left page bbox."""

    rect = getattr(cell, "rect", None)
    if rect is None:
        return None
    try:
        bbox = rect.to_top_left_origin(page_height=page_height).to_bounding_box()
    except (AttributeError, TypeError, ValueError):
        return None
    return bbox_from_obj(bbox)


def bbox_metrics(bbox: BBox | list[float] | None) -> dict[str, float | None]:
    """Return simple width/height/area metrics for a bbox list."""

    if bbox is None:
        return {"width": None, "height": None, "area": None}
    if isinstance(bbox, BBox):
        return {"width": bbox.width, "height": bbox.height, "area": bbox.width * bbox.height}

    width = abs(bbox[2] - bbox[0])
    height = abs(bbox[3] - bbox[1])
    return {"width": width, "height": height, "area": width * height}


def bbox_overlap_metrics(first: BBox | list[float] | None, second: BBox | list[float] | None) -> dict[str, float]:
    """Return overlap metrics for two bbox lists."""

    if first is None or second is None:
        return {
            "intersection_area": 0.0,
            "iou": 0.0,
            "first_coverage": 0.0,
            "second_coverage": 0.0,
        }
    first_values = first.as_list() if isinstance(first, BBox) else first
    second_values = second.as_list() if isinstance(second, BBox) else second

    left = max(min(first_values[0], first_values[2]), min(second_values[0], second_values[2]))
    right = min(max(first_values[0], first_values[2]), max(second_values[0], second_values[2]))
    top = max(min(first_values[1], first_values[3]), min(second_values[1], second_values[3]))
    bottom = min(max(first_values[1], first_values[3]), max(second_values[1], second_values[3]))

    width = max(0.0, right - left)
    height = max(0.0, bottom - top)
    intersection = width * height
    first_area = bbox_metrics(first)["area"] or 0.0
    second_area = bbox_metrics(second)["area"] or 0.0
    union = first_area + second_area - intersection

    return {
        "intersection_area": intersection,
        "iou": intersection / union if union else 0.0,
        "first_coverage": intersection / first_area if first_area else 0.0,
        "second_coverage": intersection / second_area if second_area else 0.0,
    }


def item_provenance(item: Any) -> list[dict[str, Any]]:
    """Serialize Docling item provenance."""

    records = []
    for prov in getattr(item, "prov", []) or []:
        records.append(
            {
                "page": getattr(prov, "page_no", None),
                "bbox": bbox_to_list(getattr(prov, "bbox", None)),
                "charspan": list(getattr(prov, "charspan", ()) or ()),
            }
        )
    return records


def first_prov(item: Any) -> Any | None:
    """Return the first provenance record for a Docling item."""

    prov = getattr(item, "prov", None) or []
    return prov[0] if prov else None


def page_size(page: Any) -> dict[str, float | None]:
    """Serialize a Docling page size."""

    size = getattr(page, "size", None)
    return {
        "width": float(getattr(size, "width", 0.0)) if size else None,
        "height": float(getattr(size, "height", 0.0)) if size else None,
    }


def page_ref(page_no: int, page: Any) -> PageRef:
    """Build a shared PageRef from a Docling page."""

    size = page_size(page)
    return PageRef(page_no=page_no, width=size["width"], height=size["height"])


def table_cells(item: Any) -> list[dict[str, Any]]:
    """Serialize Docling table cells."""

    data = getattr(item, "data", None)
    cells = getattr(data, "table_cells", []) if data is not None else []
    out = []
    for cell in cells:
        out.append(
            {
                "text": getattr(cell, "text", ""),
                "bbox": bbox_to_list(getattr(cell, "bbox", None)),
                "row_offset": getattr(cell, "start_row_offset_idx", None),
                "col_offset": getattr(cell, "start_col_offset_idx", None),
                "row_span": getattr(cell, "row_span", None),
                "col_span": getattr(cell, "col_span", None),
                "column_header": getattr(cell, "column_header", None),
                "row_header": getattr(cell, "row_header", None),
                "row_section": getattr(cell, "row_section", None),
            }
        )
    return out


def summarize_item(item: Any, doc: Any, level: int) -> dict[str, Any]:
    """Serialize one Docling document item."""

    record: dict[str, Any] = {
        "type": type(item).__name__,
        "label": enum_value(getattr(item, "label", None)),
        "level": level,
        "self_ref": getattr(item, "self_ref", None),
        "text": getattr(item, "text", None),
        "prov": item_provenance(item),
    }

    if isinstance(item, TableItem):
        data = getattr(item, "data", None)
        record["table"] = {
            "num_rows": getattr(data, "num_rows", None),
            "num_cols": getattr(data, "num_cols", None),
            "cells": table_cells(item),
        }
        try:
            record["table"]["markdown"] = item.export_to_markdown(doc=doc)
        except Exception as exc:  # pragma: no cover - diagnostics only
            record["table"]["markdown_error"] = str(exc)

    if isinstance(item, PictureItem):
        record["picture"] = {
            "captions": [getattr(ref, "cref", str(ref)) for ref in getattr(item, "captions", [])],
            "footnotes": [getattr(ref, "cref", str(ref)) for ref in getattr(item, "footnotes", [])],
        }

    if isinstance(item, TextItem):
        record["orig"] = getattr(item, "orig", None)

    return record


def build_page_records(doc: Any) -> list[dict[str, Any]]:
    """Build a JSON-safe page/item summary from a Docling document."""

    pages = []
    for page_no, page in sorted(getattr(doc, "pages", {}).items()):
        items = [summarize_item(item, doc, level) for item, level in doc.iterate_items(page_no=page_no)]
        labels: dict[str, int] = {}
        for item in items:
            label = str(item.get("label"))
            labels[label] = labels.get(label, 0) + 1

        pages.append(
            {
                "page": page_no,
                "size": page_size(page),
                "label_counts": labels,
                "items": items,
                "markdown": doc.export_to_markdown(page_no=page_no),
            }
        )
    return pages


def render_item_markdown(item: Any, doc: Any) -> str | None:
    """Render one Docling item into simple Markdown."""

    label = getattr(item, "label", None)
    text = (getattr(item, "text", None) or "").strip()

    if isinstance(item, TableItem):
        try:
            return item.export_to_markdown(doc=doc).strip()
        except Exception:
            return text or "[table]"

    if isinstance(item, PictureItem):
        return "<!-- image -->"

    if not text:
        return None

    if label == DocItemLabel.TITLE:
        return f"# {text}"
    if label == DocItemLabel.SECTION_HEADER:
        return f"## {text}"
    if label == DocItemLabel.LIST_ITEM:
        return f"- {text}"
    return text


def build_hybrid_markdown(doc: Any, candidates: list[dict[str, Any]]) -> str:
    """Build Docling Markdown with Surya replacements where available."""

    from .surya_pipeline import surya_replacement_text

    replacements: dict[str, str] = {}
    skipped_refs: set[str] = set()
    for candidate in candidates:
        if not candidate.get("surya"):
            continue

        replacement = surya_replacement_text(candidate)
        if not replacement:
            continue

        covered_refs = [str(ref) for ref in candidate.get("covered_self_refs", []) if ref]
        if covered_refs:
            replacements[covered_refs[0]] = replacement
            skipped_refs.update(covered_refs[1:])
            continue

        self_ref = candidate.get("self_ref")
        if self_ref:
            replacements[str(self_ref)] = replacement

    page_chunks = []
    for page_no in sorted(getattr(doc, "pages", {}).keys()):
        chunks = []
        for item, _level in doc.iterate_items(page_no=page_no):
            self_ref = str(getattr(item, "self_ref", ""))
            if self_ref in skipped_refs:
                continue

            replacement = replacements.get(self_ref)
            if replacement:
                chunks.append(replacement)
                continue

            rendered = render_item_markdown(item, doc)
            if rendered:
                chunks.append(rendered)
        page_chunks.append("\n\n".join(chunks).strip())

    return "\n\n\n<!-- Page Break -->\n\n\n".join(page_chunks).strip()


def bbox_from_list(values: list[float] | None) -> BBox | None:
    """Convert a bbox list into BBox."""

    if values is None or len(values) != 4:
        return None
    return BBox(float(values[0]), float(values[1]), float(values[2]), float(values[3]))


def page_ref_from_candidate(candidate: dict[str, Any]) -> PageRef:
    """Build PageRef from serialized candidate metadata."""

    page = candidate.get("page_ref") or {}
    return PageRef(
        page_no=int(page.get("page_no") or candidate.get("page") or 0),
        width=page.get("width"),
        height=page.get("height"),
    )


def map_image_bbox_to_page_bbox(
    image_bbox: list[float],
    image_extent: list[float],
    crop_bbox: BBox,
) -> BBox:
    """Map a Surya image-space bbox into a page-space crop bbox."""

    image_x0, image_y0, image_x1, image_y1 = [float(value) for value in image_extent]
    image_width = max(image_x1 - image_x0, 1.0)
    image_height = max(image_y1 - image_y0, 1.0)
    x0, y0, x1, y1 = [float(value) for value in image_bbox]
    return BBox(
        crop_bbox.x0 + ((x0 - image_x0) / image_width) * crop_bbox.width,
        crop_bbox.y0 + ((y0 - image_y0) / image_height) * crop_bbox.height,
        crop_bbox.x0 + ((x1 - image_x0) / image_width) * crop_bbox.width,
        crop_bbox.y0 + ((y1 - image_y0) / image_height) * crop_bbox.height,
    )


def build_surya_ocr_lines(candidate: dict[str, Any]) -> list[OcrLine]:
    """Build page-coordinate OcrLines from one Surya-routed candidate."""

    from .surya_pipeline import normalize_surya_markup, surya_replacement_text

    surya = candidate.get("surya") or {}
    page = page_ref_from_candidate(candidate)

    if candidate.get("reason") == "docling_formula_cluster_zone":
        text = surya_replacement_text(candidate)
        bbox = bbox_from_list(candidate.get("bbox_top_left") or candidate.get("bbox"))
        if not text or bbox is None:
            return []
        return [
            OcrLine(
                text=text,
                page=page,
                bbox=bbox,
                source_bbox=bbox_from_list(candidate.get("bbox")),
                metadata={
                    "source": "surya_formula_zone",
                    "candidate_id": candidate.get("candidate_id"),
                },
            )
        ]

    crop_bbox = bbox_from_list(candidate.get("crop_bbox_top_left"))
    if crop_bbox is None:
        crop_bbox = bbox_from_list(candidate.get("bbox_top_left") or candidate.get("bbox"))
    if crop_bbox is None:
        return []

    image_bbox = surya.get("image_bbox")
    if not image_bbox or len(image_bbox) != 4:
        width, height = candidate.get("crop_detection_size_px") or candidate.get("crop_size_px") or [1, 1]
        image_bbox = [0.0, 0.0, float(width), float(height)]

    lines: list[OcrLine] = []
    for line in surya.get("text_lines", []) or []:
        text = normalize_surya_markup(line.get("text", ""))
        bbox = line.get("bbox")
        if not text or not bbox or len(bbox) != 4:
            continue
        lines.append(
            OcrLine(
                text=text,
                page=page,
                bbox=map_image_bbox_to_page_bbox(bbox, image_bbox, crop_bbox),
                source_bbox=bbox_from_list(bbox),
                confidence=line.get("confidence"),
                metadata={
                    "source": "surya_inline_crop",
                    "candidate_id": candidate.get("candidate_id"),
                },
            )
        )
    return lines


def routed_regions_by_page(candidates: list[dict[str, Any]]) -> dict[int, list[BBox]]:
    """Return original-page regions whose text is replaced by Surya."""

    regions: dict[int, list[BBox]] = {}
    for candidate in candidates:
        if not candidate.get("surya"):
            continue
        page_no = int(candidate.get("page") or 0)
        bbox = bbox_from_list(candidate.get("bbox_top_left") or candidate.get("bbox"))
        if page_no > 0 and bbox is not None:
            regions.setdefault(page_no, []).append(bbox)
    return regions


def cell_is_replaced_by_surya(cell_bbox: BBox, routed_regions: list[BBox]) -> bool:
    """Return whether Surya replaces most of this Docling text cell."""

    return any(
        bbox_overlap_metrics(cell_bbox, region)["first_coverage"] >= 0.50
        for region in routed_regions
    )


def page_layout_text_cells(page: Any) -> list[Any]:
    """Return all post-layout text cells for a page without duplicates."""

    layout = getattr(getattr(page, "predictions", None), "layout", None)
    roots = getattr(layout, "clusters", []) if layout is not None else []
    cells: list[Any] = []
    seen: set[tuple[Any, ...]] = set()

    def add_cell(cell: Any) -> None:
        rect = getattr(cell, "rect", None)
        bbox = rect.to_bounding_box() if rect is not None else None
        bbox_values = tuple(bbox.as_tuple()) if bbox is not None else ()
        key = (
            getattr(cell, "index", None),
            str(getattr(cell, "text", "") or ""),
            bbox_values,
        )
        if key in seen:
            return
        seen.add(key)
        cells.append(cell)

    def visit_cluster(cluster: Any) -> None:
        for cell in getattr(cluster, "cells", []) or []:
            add_cell(cell)
        for child in getattr(cluster, "children", []) or []:
            visit_cluster(child)

    for cluster in roots:
        visit_cluster(cluster)
    for cell in getattr(page, "cells", []) or []:
        add_cell(cell)
    return cells


def build_hybrid_ocr_lines(conv_res: Any, candidates: list[dict[str, Any]]) -> list[OcrLine]:
    """Build page-coordinate text records from Docling cells and Surya results."""

    lines: list[OcrLine] = []
    for candidate in candidates:
        if not candidate.get("surya"):
            continue
        lines.extend(build_surya_ocr_lines(candidate))

    replaced_regions = routed_regions_by_page(candidates)
    for page in getattr(conv_res, "pages", []) or []:
        page_no = int(getattr(page, "page_no", 0))
        page_height = float(getattr(getattr(page, "size", None), "height", 0.0))
        if page_no <= 0 or page_height <= 0:
            continue

        for cell in page_layout_text_cells(page):
            text = str(getattr(cell, "text", "") or "").strip()
            bbox = text_cell_bbox_to_top_left(cell, page_height)
            if not text or bbox is None:
                continue
            if cell_is_replaced_by_surya(bbox, replaced_regions.get(page_no, [])):
                continue

            lines.append(
                OcrLine(
                    text=text,
                    page=page_ref(page_no, page),
                    bbox=bbox,
                    source_bbox=bbox,
                    confidence=getattr(cell, "confidence", None),
                    metadata={
                        "source": "docling_text_cell",
                        "from_ocr": bool(getattr(cell, "from_ocr", False)),
                        "cell_index": getattr(cell, "index", None),
                    },
                )
            )
    return lines


def text_cell_record(cell: Any) -> dict[str, Any]:
    """Serialize a Docling layout text cell."""

    text = getattr(cell, "text", None)
    return {
        "text": text,
        "text_preview": text[:160] if isinstance(text, str) else None,
        "bbox": bbox_to_list(getattr(cell, "bbox", None)),
        "confidence": getattr(cell, "confidence", None),
    }


def cluster_record(cluster: Any, include_cells: bool) -> dict[str, Any]:
    """Serialize a Docling internal layout cluster."""

    bbox = bbox_to_list(getattr(cluster, "bbox", None))
    raw_bbox = getattr(cluster, "bbox", None)
    cells = getattr(cluster, "cells", []) or []
    children = getattr(cluster, "children", []) or []
    record: dict[str, Any] = {
        "id": getattr(cluster, "id", None),
        "label": enum_value(getattr(cluster, "label", None)),
        "confidence": getattr(cluster, "confidence", None),
        "bbox": bbox,
        "bbox_origin": bbox_origin(raw_bbox),
        "bbox_top_left": bbox,
        **bbox_metrics(bbox),
        "cell_count": len(cells),
        "child_count": len(children),
    }

    if cells:
        text = " ".join(
            getattr(cell, "text", "")
            for cell in cells
            if getattr(cell, "text", None)
        ).strip()
        record["text_preview"] = text[:240] if text else None
    if include_cells:
        record["cells"] = [text_cell_record(cell) for cell in cells]
    if children:
        record["children"] = [
            cluster_record(child, include_cells=include_cells) for child in children
        ]
    return record


def page_layout_clusters(page: Any, include_cells: bool) -> list[dict[str, Any]]:
    """Serialize internal layout clusters for a Docling page."""

    layout = getattr(getattr(page, "predictions", None), "layout", None)
    clusters = getattr(layout, "clusters", []) if layout is not None else []
    return [cluster_record(cluster, include_cells=include_cells) for cluster in clusters]


def candidate_cluster_overlaps(candidate: dict[str, Any], clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return layout clusters overlapping a routed candidate."""

    candidate_bbox = candidate.get("bbox_top_left") or candidate.get("bbox")
    overlaps = []
    for cluster in clusters:
        metrics = bbox_overlap_metrics(candidate_bbox, cluster.get("bbox_top_left") or cluster.get("bbox"))
        if metrics["intersection_area"] <= 0:
            continue
        overlaps.append(
            {
                "cluster_id": cluster.get("id"),
                "label": cluster.get("label"),
                "confidence": cluster.get("confidence"),
                "bbox": cluster.get("bbox"),
                **metrics,
            }
        )
    return sorted(
        overlaps,
        key=lambda item: (
            item["first_coverage"],
            item["second_coverage"],
            item["iou"],
            item["intersection_area"],
        ),
        reverse=True,
    )


def json_safe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop private runtime objects from route candidates."""

    return [
        {key: value for key, value in candidate.items() if not key.startswith("_")}
        for candidate in candidates
    ]


def math_route_for_item(item: Any, page: Any, level: int, threshold: float) -> dict[str, Any] | None:
    """Return a Surya route candidate for math-like Docling text items."""

    if not isinstance(item, TextItem):
        return None

    text = getattr(item, "text", "") or ""
    score = mathematics_score(text)
    if score < threshold:
        return None

    prov = first_prov(item)
    if prov is None:
        return None

    bbox = bbox_from_obj(getattr(prov, "bbox", None))
    if bbox is None:
        return None
    page_height = float(getattr(getattr(page, "size", None), "height", 0.0)) or None
    bbox_top_left = bbox_to_top_left(getattr(prov, "bbox", None), page_height)

    return {
        "_item": item,
        "_prov_bbox": getattr(prov, "bbox", None),
        "page": getattr(prov, "page_no", None),
        "page_ref": page_ref(int(getattr(prov, "page_no", 0)), page).__dict__,
        "label": enum_value(getattr(item, "label", None)),
        "type": type(item).__name__,
        "level": level,
        "self_ref": getattr(item, "self_ref", None),
        "score": score,
        "threshold": threshold,
        "reason": "text_math_score",
        "bbox": bbox_list_from_model(bbox),
        "bbox_origin": bbox_origin(getattr(prov, "bbox", None)),
        "bbox_top_left": bbox_list_from_model(bbox_top_left),
        "charspan": list(getattr(prov, "charspan", ()) or ()),
        "text": text,
        "text_preview": text[:240],
        "route": "surya_crop",
    }


def vertical_gap(first: Any, second: Any) -> float:
    """Return the vertical gap between two Docling bounding boxes."""

    if first.coord_origin != second.coord_origin:
        raise ValueError("BoundingBoxes have different CoordOrigin")
    if first.overlaps_vertically(second):
        return 0.0
    if getattr(first.coord_origin, "name", None) == "TOPLEFT":
        return max(second.t - first.b, first.t - second.b, 0.0)
    return max(first.b - second.t, second.b - first.t, 0.0)


def should_merge_formula_boxes(first: Any, second: Any, max_vertical_gap: float) -> bool:
    """Return whether adjacent Docling formula clusters should become one zone."""

    gap = vertical_gap(first, second)
    if gap > max_vertical_gap:
        return False

    min_width = max(min(first.width, second.width), 1.0)
    horizontal_overlap_ratio = first.x_overlap_with(second) / min_width
    left_aligned = abs(first.l - second.l) <= 36.0
    right_aligned = abs(first.r - second.r) <= 36.0
    return horizontal_overlap_ratio >= 0.10 or left_aligned or right_aligned


def merge_formula_clusters(clusters: list[Any], max_vertical_gap: float) -> list[dict[str, Any]]:
    """Merge raw Docling formula clusters into larger formula zones."""

    formula_clusters = [
        cluster
        for cluster in clusters
        if getattr(cluster, "label", None) == DocItemLabel.FORMULA
        and getattr(cluster, "bbox", None) is not None
    ]
    formula_clusters.sort(key=lambda cluster: (cluster.bbox.t, cluster.bbox.l))

    zones: list[dict[str, Any]] = []
    for cluster in formula_clusters:
        cluster_bbox = cluster.bbox
        matching_indexes = [
            index
            for index, zone in enumerate(zones)
            if should_merge_formula_boxes(
                zone["bbox"],
                cluster_bbox,
                max_vertical_gap=max_vertical_gap,
            )
        ]

        if not matching_indexes:
            zones.append({"bbox": cluster_bbox, "clusters": [cluster]})
            continue

        first_index = matching_indexes[0]
        zones[first_index]["clusters"].append(cluster)
        for index in reversed(matching_indexes[1:]):
            zones[first_index]["clusters"].extend(zones[index]["clusters"])
            zones.pop(index)
        zones[first_index]["bbox"] = BoundingBox.enclosing_bbox(
            [item.bbox for item in zones[first_index]["clusters"]]
        )

    zones.sort(key=lambda zone: (zone["bbox"].t, zone["bbox"].l))
    return zones


def covered_item_refs_for_zone(doc: Any, page_no: int, zone_bbox: Any, page_height: float) -> list[str]:
    """Return Docling item refs mostly covered by one formula zone."""

    refs = []
    zone_bbox_top_left = bbox_to_list(zone_bbox)
    for item, _level in doc.iterate_items(page_no=page_no):
        prov = first_prov(item)
        if prov is None:
            continue

        item_bbox = getattr(prov, "bbox", None)
        item_bbox_top_left = bbox_to_top_left_list(item_bbox, page_height)
        overlap = bbox_overlap_metrics(item_bbox_top_left, zone_bbox_top_left)
        if overlap["first_coverage"] < 0.25:
            continue

        label = getattr(item, "label", None)
        if label in {DocItemLabel.FORMULA, DocItemLabel.TEXT}:
            self_ref = getattr(item, "self_ref", None)
            if self_ref:
                refs.append(str(self_ref))
    return refs


def formula_zone_route_plan(doc: Any, conv_res: Any, max_vertical_gap: float) -> list[dict[str, Any]]:
    """Build route candidates from Docling internal formula layout clusters."""

    candidates = []
    for page in getattr(conv_res, "pages", []) or []:
        page_no = int(getattr(page, "page_no"))
        page_height = float(getattr(getattr(page, "size", None), "height", 0.0))
        layout = getattr(getattr(page, "predictions", None), "layout", None)
        clusters = getattr(layout, "clusters", []) if layout is not None else []
        zones = merge_formula_clusters(clusters, max_vertical_gap=max_vertical_gap)
        for zone_index, zone in enumerate(zones, start=1):
            zone_bbox = zone["bbox"]
            zone_bbox_model = bbox_from_obj(zone_bbox)
            zone_bbox_top_left = bbox_to_top_left(zone_bbox, page_height)
            zone_clusters = zone["clusters"]
            text_preview = " ".join(
                " ".join(
                    getattr(cell, "text", "")
                    for cell in getattr(cluster, "cells", []) or []
                    if getattr(cell, "text", None)
                ).strip()
                for cluster in zone_clusters
            ).strip()
            confidences = [
                float(getattr(cluster, "confidence"))
                for cluster in zone_clusters
                if getattr(cluster, "confidence", None) is not None
            ]
            score = sum(confidences) / len(confidences) if confidences else None
            candidates.append(
                {
                    "_prov_bbox": zone_bbox,
                    "page": page_no,
                    "page_ref": page_ref(page_no, page).__dict__,
                    "label": "formula_zone",
                    "type": "FormulaZone",
                    "level": 1,
                    "self_ref": None,
                    "covered_self_refs": covered_item_refs_for_zone(
                        doc=doc,
                        page_no=page_no,
                        zone_bbox=zone_bbox,
                        page_height=page_height,
                    ),
                    "score": score,
                    "threshold": None,
                    "reason": "docling_formula_cluster_zone",
                    "bbox": bbox_list_from_model(zone_bbox_model),
                    "bbox_origin": bbox_origin(zone_bbox),
                    "bbox_top_left": bbox_list_from_model(zone_bbox_top_left),
                    "cluster_ids": [getattr(cluster, "id", None) for cluster in zone_clusters],
                    "cluster_confidences": confidences,
                    "cluster_count": len(zone_clusters),
                    "zone_index": zone_index,
                    "text": text_preview,
                    "text_preview": text_preview[:240],
                    "route": "surya_crop",
                }
            )
    return candidates


def build_math_route_plan(doc: Any, conv_res: Any, threshold: float, formula_zone_gap: float) -> list[dict[str, Any]]:
    """Build a sorted Docling math route plan without invoking Surya."""

    candidates = []
    for page_no, page in sorted(getattr(doc, "pages", {}).items()):
        for item, level in doc.iterate_items(page_no=page_no):
            route = math_route_for_item(
                item=item,
                page=page,
                level=level,
                threshold=threshold,
            )
            if route is not None:
                candidates.append(route)
    candidates.extend(
        formula_zone_route_plan(
            doc=doc,
            conv_res=conv_res,
            max_vertical_gap=formula_zone_gap,
        )
    )
    candidates.sort(
        key=lambda candidate: (
            int(candidate.get("page") or 0),
            (candidate.get("bbox_top_left") or candidate.get("bbox") or [0, 0, 0, 0])[1],
            (candidate.get("bbox_top_left") or candidate.get("bbox") or [0, 0, 0, 0])[0],
        )
    )
    for index, candidate in enumerate(candidates, start=1):
        candidate["candidate_id"] = f"p{candidate['page']:03d}_m{index:03d}"
    return candidates


def build_docling_debug_records(
    conv_res: Any,
    candidates: list[dict[str, Any]],
    include_cells: bool = False,
) -> dict[str, Any]:
    """Build debug records for Docling internal layout and route candidates."""

    pages = []
    clusters_by_page: dict[int, list[dict[str, Any]]] = {}
    for page in getattr(conv_res, "pages", []) or []:
        page_no = int(getattr(page, "page_no"))
        clusters = page_layout_clusters(page, include_cells=include_cells)
        clusters_by_page[page_no] = clusters
        label_counts: dict[str, int] = {}
        for cluster in clusters:
            label = str(cluster.get("label"))
            label_counts[label] = label_counts.get(label, 0) + 1

        pages.append(
            {
                "page": page_no,
                "layout_cluster_count": len(clusters),
                "layout_cluster_label_counts": label_counts,
                "layout_clusters": clusters,
            }
        )

    routed_candidates = []
    for candidate in json_safe_candidates(candidates):
        page_clusters = clusters_by_page.get(int(candidate.get("page") or 0), [])
        routed_candidates.append(
            {
                "candidate_id": candidate.get("candidate_id"),
                "page": candidate.get("page"),
                "reason": candidate.get("reason"),
                "label": candidate.get("label"),
                "bbox": candidate.get("bbox"),
                "bbox_origin": candidate.get("bbox_origin"),
                "bbox_top_left": candidate.get("bbox_top_left"),
                "crop_bbox": candidate.get("crop_bbox"),
                "crop_bbox_top_left": candidate.get("crop_bbox_top_left"),
                "crop_detection_size_px": candidate.get("crop_detection_size_px"),
                "crop_size_px": candidate.get("crop_size_px"),
                "covered_self_refs": candidate.get("covered_self_refs"),
                "cluster_ids": candidate.get("cluster_ids"),
                "cluster_count": candidate.get("cluster_count"),
                **bbox_metrics(candidate.get("bbox_top_left") or candidate.get("bbox")),
                "overlapping_layout_clusters": candidate_cluster_overlaps(
                    candidate,
                    page_clusters,
                ),
            }
        )

    return {
        "note": (
            "These are Docling internal layout clusters from conv_res.pages[*]."
            "predictions.layout, not aggregate document confidence scores."
        ),
        "pages": pages,
        "routed_candidates": routed_candidates,
    }


def cleanup_prepared_crop_images(candidates: list[dict[str, Any]]) -> None:
    """Close in-memory PIL crop images and remove private Docling objects."""

    for candidate in candidates:
        image = candidate.pop("_surya_image", None)
        if image is not None:
            image.close()
        highres_image = candidate.pop("_surya_highres_image", None)
        if highres_image is not None:
            highres_image.close()
        candidate.pop("_item", None)
        candidate.pop("_prov_bbox", None)


def prepare_math_crop_images(
    conv_res: Any,
    candidates: list[dict[str, Any]],
    detection_scale: float,
    recognition_scale: float,
    expansion_factor: float,
    debug_crops_dir: Path | None = None,
) -> None:
    """Render routed math candidates through Docling page.get_image()."""

    if not candidates:
        return

    if debug_crops_dir is not None:
        debug_crops_dir.mkdir(parents=True, exist_ok=True)

    pages_by_no = {page.page_no: page for page in conv_res.pages}
    for candidate in candidates:
        prov_bbox = candidate.get("_prov_bbox")
        if prov_bbox is None:
            continue

        expanded_bbox = prov_bbox.expand_by_scale(expansion_factor, expansion_factor)
        page = pages_by_no.get(int(candidate["page"]))
        if page is None:
            candidate["crop_error"] = "Page not found in conversion result"
            continue

        page_height = float(getattr(getattr(page, "size", None), "height", 0.0)) or None
        detection_image = page.get_image(scale=detection_scale, cropbox=expanded_bbox)
        recognition_image = page.get_image(scale=recognition_scale, cropbox=expanded_bbox)
        if detection_image is None or recognition_image is None:
            candidate["crop_error"] = "Docling page get_image returned None"
            continue

        candidate["_surya_image"] = detection_image
        candidate["_surya_highres_image"] = recognition_image
        candidate["crop_bbox"] = bbox_to_list(expanded_bbox)
        candidate["crop_bbox_top_left"] = bbox_to_top_left_list(expanded_bbox, page_height)
        candidate["crop_bbox_origin"] = bbox_origin(expanded_bbox)
        candidate["crop_detection_scale"] = detection_scale
        candidate["crop_recognition_scale"] = recognition_scale
        candidate["crop_detection_size_px"] = list(detection_image.size)
        candidate["crop_size_px"] = list(recognition_image.size)

        if debug_crops_dir is not None:
            crop_path = debug_crops_dir / f"{candidate['candidate_id']}.png"
            recognition_image.save(crop_path)
            candidate["crop_path"] = str(crop_path)


def write_json(path: Path, data: Any) -> None:
    """Write indented UTF-8 JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def cleanup_cuda() -> None:
    """Release Python and PyTorch GPU cache when available."""

    gc.collect()
    try:
        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        pass


def cleanup_conversion_backends(conv_res: Any) -> None:
    """Unload Docling backends and image caches."""

    for page in getattr(conv_res, "pages", []) or []:
        backend = getattr(page, "_backend", None)
        if backend is not None:
            backend.unload()
            page._backend = None
        page._image_cache = {}

    input_doc = getattr(conv_res, "input", None)
    input_backend = getattr(input_doc, "_backend", None)
    if input_backend is not None:
        input_backend.unload()


class DoclingHybridPipeline:
    """Run the Docling-first hybrid extraction path."""

    def __init__(self, config: ExtractConfig | None = None) -> None:
        self.config = config or ExtractConfig()

    def run(self, request: RunRequest) -> RunResult:
        started = time.monotonic()
        log_progress("start", f"input PDF: {request.input_pdf}")
        self.require_gpu()
        log_progress("docling", "analyzing document layout")
        result = self.convert(request)
        doc = result.document
        log_progress("docling", f"layout complete: {len(getattr(result, 'pages', []) or [])} pages")
        math_route_plan: list[dict[str, Any]] = []
        try:
            report, math_route_plan = self.build_report(
                request=request,
                result=result,
                doc=doc,
            )
            if request.markdown_out is not None:
                log_progress("text", "assembling Markdown")
                if report["math_routing"]["surya_crops_run"]:
                    markdown = build_hybrid_markdown(doc, math_route_plan)
                else:
                    markdown = doc.export_to_markdown(
                        page_break_placeholder="\n\n<!-- Page Break -->\n\n",
                    )
                request.markdown_out.parent.mkdir(parents=True, exist_ok=True)
                request.markdown_out.write_text(markdown, encoding="utf-8")
                log_progress("text", f"wrote Markdown: {request.markdown_out}")

            rewrite_summary = None
            if request.pdf_out is not None:
                from .pdf_rewrite import OcrLinePdfRewriter

                log_progress("pdf", "building page-coordinate text layer")
                ocr_lines = build_hybrid_ocr_lines(result, math_route_plan)
                log_progress("pdf", f"prepared {len(ocr_lines)} positioned text lines")
                rewrite_summary = OcrLinePdfRewriter(
                    input_pdf=request.input_pdf,
                    output_pdf=request.pdf_out,
                    lines=ocr_lines,
                    config=self.config,
                ).rewrite(policy=request.rewrite_policy)
                report["ocr_pdf_rewrite"] = {
                    "output_pdf": rewrite_summary.output_pdf,
                    "line_count": len(ocr_lines),
                    "page_actions": rewrite_summary.page_actions,
                    "page_classes": rewrite_summary.page_classes,
                }

            if request.json_out is not None:
                write_json(request.json_out, report)

            if request.pdf_out:
                log_progress("pdf", f"wrote OCR PDF: {request.pdf_out}")
            if request.json_out:
                log_progress("json", f"wrote JSON: {request.json_out}")
            log_progress("done", f"completed in {time.monotonic() - started:.1f}s")
            return RunResult(
                markdown_out=request.markdown_out,
                pdf_out=request.pdf_out,
                json_out=request.json_out,
                report=report,
            )
        finally:
            cleanup_cuda()
            cleanup_prepared_crop_images(math_route_plan)
            cleanup_conversion_backends(result)

    def require_gpu(self) -> None:
        """Fail rather than silently falling back to CPU."""

        if self.config.docling.device != "cuda":
            raise RuntimeError("CPU fallback is disabled. Configure Docling device as cuda.")

        if torch is None:
            raise RuntimeError("PyTorch is required for cuda/ROCm execution.")
        if not torch.cuda.is_available():
            raise RuntimeError(
                "PyTorch does not see a CUDA/ROCm GPU in this shell. Run from the elevated shell."
            )

    def convert(self, request: RunRequest) -> Any:
        """Run Docling conversion for the requested PDF/pages."""

        docling = self.config.docling
        options = PdfPipelineOptions()
        options.do_ocr = docling.do_ocr
        options.do_table_structure = docling.do_tables
        options.do_formula_enrichment = docling.do_formulas
        options.do_picture_description = False
        options.generate_page_images = False
        options.layout_batch_size = docling.layout_batch_size
        options.ocr_batch_size = docling.ocr_batch_size
        options.table_batch_size = docling.table_batch_size
        options.queue_max_size = docling.queue_max_size
        options.accelerator_options = AcceleratorOptions(
            device=AcceleratorDevice(docling.device),
            num_threads=docling.threads,
        )
        options.table_structure_options = TableStructureOptions(
            do_cell_matching=True,
            mode=TableFormerMode.ACCURATE,
        )
        if docling.do_ocr:
            options.ocr_options = TesseractCliOcrOptions(
                lang=list(docling.ocr_lang),
                force_full_page_ocr=docling.force_full_page_ocr,
            )

        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=options,
                    pipeline_cls=KeepBackendPdfPipeline,
                )
            }
        )
        return converter.convert(request.input_pdf, page_range=parse_page_range(request.pages))

    def build_report(self, request: RunRequest, result: Any, doc: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Build the current Docling-only JSON payload."""

        math_route_plan = build_math_route_plan(
            doc=doc,
            conv_res=result,
            threshold=self.config.docling.math_threshold,
            formula_zone_gap=self.config.docling.formula_zone_gap,
        )
        log_progress("route", f"found {len(math_route_plan)} math candidates")
        detection_crop_scale = self.config.docling.crop_detection_dpi / 72.0
        recognition_crop_scale = self.config.docling.crop_recognition_dpi / 72.0
        if math_route_plan:
            log_progress("crop", f"rendering {len(math_route_plan)} candidate regions")
        prepare_math_crop_images(
            conv_res=result,
            candidates=math_route_plan,
            detection_scale=detection_crop_scale,
            recognition_scale=recognition_crop_scale,
            expansion_factor=self.config.docling.crop_expansion,
            debug_crops_dir=request.crops_dir if request.save_crops else None,
        )
        surya_batches: list[dict[str, Any]] = []
        run_surya = (
            self.config.surya.enabled_for_math_crops
            and request.run_surya_math
            and bool(math_route_plan)
        )
        if run_surya:
            from .surya_pipeline import SuryaCropRecognizer

            log_progress("surya", f"recognizing {len(math_route_plan)} routed regions")
            surya_batches = SuryaCropRecognizer(self.config).recognize(math_route_plan)
            log_progress("surya", "routed-region recognition complete")

        math_routing = {
            "threshold": self.config.docling.math_threshold,
            "formula_zone_gap": self.config.docling.formula_zone_gap,
            "crop_expansion": self.config.docling.crop_expansion,
            "crop_detection_dpi": self.config.docling.crop_detection_dpi,
            "crop_detection_scale": detection_crop_scale,
            "crop_dpi": self.config.docling.crop_recognition_dpi,
            "crop_scale": recognition_crop_scale,
            "crop_pdf_dpi": self.config.docling.crop_pdf_dpi,
            "crops_prepared": True,
            "crops_saved": request.save_crops,
            "crops_dir": str(request.crops_dir) if request.save_crops else None,
            "surya_crops_run": run_surya,
            "surya_batches": surya_batches,
            "candidate_count": len(math_route_plan),
            "candidates": json_safe_candidates(math_route_plan),
        }

        payload = {
            "source": str(request.input_pdf),
            "page_range": list(parse_page_range(request.pages)),
            "status": enum_value(getattr(result, "status", None)),
            "errors": [str(error) for error in getattr(result, "errors", [])],
            "confidence": getattr(result, "confidence", None).model_dump(mode="json")
            if getattr(result, "confidence", None) is not None
            else None,
            "workflow": "docling-hybrid",
            "math_routing": math_routing,
            "pages": build_page_records(doc),
        }
        if request.debug:
            payload["docling_debug"] = build_docling_debug_records(
                conv_res=result,
                candidates=math_route_plan,
                include_cells=False,
            )
        return payload, math_route_plan
