"""Surya OCR pipeline helpers."""

from __future__ import annotations

import gc
import html
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from PIL import Image

from .config import ExtractConfig, OutputMode
from .models import RunRequest, RunResult


BLOCK_MATH_RE = re.compile(r'<math\s+display=["\']block["\']\s*>(.*?)</math>', re.DOTALL)
INLINE_MATH_RE = re.compile(r"<math\s*>(.*?)</math>", re.DOTALL)
ITALIC_RE = re.compile(r"<i>(.*?)</i>", re.DOTALL)


def set_surya_env_defaults(config: ExtractConfig) -> None:
    """Set conservative Surya/PyTorch defaults before importing Surya models."""

    surya = config.surya
    os.environ.setdefault("DETECTOR_BATCH_SIZE", str(surya.detector_batch_size))
    os.environ.setdefault("RECOGNITION_BATCH_SIZE", str(surya.recognition_batch_size))
    os.environ.setdefault("TORCH_DEVICE", surya.torch_device)
    os.environ.setdefault("MIOPEN_FIND_MODE", surya.miopen_find_mode)
    os.environ.setdefault("PYTORCH_TUNABLEOP_ENABLED", surya.pytorch_tunableop_enabled)


def cleanup_gpu_memory() -> None:
    """Release Python and PyTorch GPU cache where available."""

    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        pass


def cleanup_gpu_memory_seconds() -> float:
    """Release memory and return elapsed cleanup time."""

    start = time.monotonic()
    cleanup_gpu_memory()
    return time.monotonic() - start


def synchronize_gpu() -> None:
    """Synchronize queued GPU work so timings reflect actual execution."""

    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.synchronize()
    except Exception:
        pass


def is_oom_error(error: Exception) -> bool:
    """Return whether an exception looks like a CUDA/ROCm memory failure."""

    text = str(error).lower()
    return "out of memory" in text or "outofmemoryerror" in text or "hip out of memory" in text


def json_dumps(payload: Any) -> str:
    """Dump JSON with stable formatting."""

    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def chunk_list(items: list[Any], chunk_size: int) -> list[list[Any]]:
    """Split a list into stable chunks."""

    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    return [items[start : start + chunk_size] for start in range(0, len(items), chunk_size)]


def serialize_surya_line(line: Any) -> dict[str, Any]:
    """Convert a Surya line object to JSON-safe data."""

    return {
        "text": getattr(line, "text", None),
        "bbox": getattr(line, "bbox", None),
        "polygon": getattr(line, "polygon", None),
        "confidence": getattr(line, "confidence", None),
    }


def serialize_surya_prediction(prediction: Any) -> dict[str, Any]:
    """Convert a Surya prediction object to JSON-safe data."""

    if hasattr(prediction, "model_dump"):
        return prediction.model_dump(mode="json")
    if hasattr(prediction, "dict"):
        return prediction.dict()

    text_lines = getattr(prediction, "text_lines", None) or []
    return {
        "text": getattr(prediction, "text", None),
        "text_lines": [serialize_surya_line(line) for line in text_lines],
        "raw_type": type(prediction).__name__,
    }


def normalize_surya_markup(text: str) -> str:
    """Convert Surya XML-like markup into Markdown-ish text."""

    converted = html.unescape(text.strip())
    converted = BLOCK_MATH_RE.sub(
        lambda match: "\n\n$$\n" + match.group(1).strip() + "\n$$\n\n",
        converted,
    )
    converted = INLINE_MATH_RE.sub(
        lambda match: "$" + match.group(1).strip() + "$",
        converted,
    )
    converted = ITALIC_RE.sub(
        lambda match: "*" + match.group(1).strip() + "*",
        converted,
    )
    return converted.strip()


def surya_replacement_text(candidate: dict[str, Any]) -> str | None:
    """Return Markdown replacement text from one candidate's Surya result."""

    surya = candidate.get("surya") or {}
    lines = surya.get("text_lines") or []
    line_texts = [line.get("text", "").strip() for line in lines if line.get("text")]
    if line_texts:
        return normalize_surya_markup(" ".join(line_texts)).strip()

    text = (surya.get("text") or "").strip()
    if text:
        return normalize_surya_markup(text).strip()
    return None


def page_to_markdown(page: dict[str, Any], page_index: int) -> str:
    """Serialize one full-page Surya prediction to Markdown."""

    lines: list[str] = []
    for line in page.get("text_lines", []):
        text = line.get("text", "")
        if text.strip():
            lines.append(normalize_surya_markup(text))

    page_markdown = "\n".join(line for line in lines if line)
    return f"<!-- Page {page_index + 1} -->\n\n{page_markdown}".rstrip()


def predictions_to_markdown(predictions: list[dict[str, Any]], page_indexes: list[int]) -> str:
    """Serialize full-page Surya predictions to Markdown."""

    if len(predictions) != len(page_indexes):
        raise ValueError(
            f"Surya returned {len(predictions)} pages for {len(page_indexes)} inputs"
        )
    return "\n\n".join(
        page_to_markdown(page, page_index)
        for page, page_index in zip(predictions, page_indexes)
    ).rstrip()


def parse_page_selection(pages: str | None, page_count: int) -> list[int]:
    """Parse one-based pages/ranges into zero-based page indexes."""

    if not pages:
        return list(range(page_count))

    selected: list[int] = []
    for part in pages.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if start < 1 or end < start:
                raise ValueError("page ranges must be one-based, e.g. 1, 3, or 3-8")
            selected.extend(range(start - 1, end))
        else:
            page_no = int(part)
            if page_no < 1:
                raise ValueError("page numbers must be one-based")
            selected.append(page_no - 1)

    if not selected:
        raise ValueError("--pages did not contain any page numbers")
    for page_index in selected:
        if page_index >= page_count:
            raise ValueError(f"Page {page_index + 1} is outside the PDF's {page_count} pages")
    return selected


def page_labels(page_indexes: list[int]) -> str:
    """Return one-based page labels for logs."""

    return ",".join(str(page_index + 1) for page_index in page_indexes)


def write_crop_batch_pdf(
    batch: list[dict[str, Any]],
    pdf_path: Path,
    image_dpi: int,
) -> None:
    """Embed crop images onto normal US-letter PDF pages for Surya."""

    pages = []
    page_width = int(8.5 * image_dpi)
    page_height = int(11.0 * image_dpi)
    margin = int(0.75 * image_dpi)
    max_width = page_width - 2 * margin
    max_height = page_height - 2 * margin
    try:
        for candidate in batch:
            crop = candidate["_surya_highres_image"].convert("RGB")
            scale = min(max_width / crop.width, max_height / crop.height, 2.5)
            placed_size = (
                max(1, round(crop.width * scale)),
                max(1, round(crop.height * scale)),
            )
            resized = crop.resize(placed_size, Image.Resampling.LANCZOS)
            page = Image.new("RGB", (page_width, page_height), "white")
            position = (
                (page_width - resized.width) // 2,
                (page_height - resized.height) // 2,
            )
            page.paste(resized, position)
            candidate["surya_pdf_page_size_px"] = [page_width, page_height]
            candidate["surya_pdf_placement_px"] = [
                position[0],
                position[1],
                resized.width,
                resized.height,
            ]
            candidate["surya_pdf_scale"] = scale
            pages.append(page)
            crop.close()
            resized.close()

        if not pages:
            raise ValueError("Cannot write an empty crop batch PDF")
        pages[0].save(
            pdf_path,
            "PDF",
            save_all=True,
            append_images=pages[1:],
            resolution=float(image_dpi),
        )
    finally:
        for page in pages:
            page.close()


class SuryaSession:
    """Own Surya predictor lifecycle and GPU cleanup."""

    def __init__(self, config: ExtractConfig | None = None) -> None:
        self.config = config or ExtractConfig()
        self.foundation_predictor: Any | None = None
        self.detection_predictor: Any | None = None
        self.recognition_predictor: Any | None = None
        self.task_names: Any | None = None

    def __enter__(self) -> "SuryaSession":
        set_surya_env_defaults(self.config)

        from surya.common.surya.schema import TaskNames
        from surya.detection import DetectionPredictor
        from surya.foundation import FoundationPredictor
        from surya.recognition import RecognitionPredictor

        self.task_names = TaskNames
        start = time.monotonic()
        self.foundation_predictor = FoundationPredictor()
        self.detection_predictor = DetectionPredictor()
        self.recognition_predictor = RecognitionPredictor(self.foundation_predictor)
        self.model_seconds = time.monotonic() - start
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.foundation_predictor = None
        self.detection_predictor = None
        self.recognition_predictor = None
        cleanup_gpu_memory()

    def predictors(self) -> tuple[Any, Any]:
        """Return loaded recognition/detection predictors."""

        if self.recognition_predictor is None or self.detection_predictor is None:
            raise RuntimeError("Surya predictors have not been loaded.")
        return self.recognition_predictor, self.detection_predictor

    def recognize_images(self, batch: list[dict[str, Any]]) -> list[Any]:
        """Run Surya on direct PIL crop inputs."""

        recognition_predictor, detection_predictor = self.predictors()
        images = []
        highres_images = []
        try:
            for candidate in batch:
                images.append(candidate["_surya_image"].convert("RGB"))
                highres_images.append(candidate["_surya_highres_image"].convert("RGB"))

            return recognition_predictor(
                images,
                task_names=[self.task_names.ocr_with_boxes] * len(images),
                det_predictor=detection_predictor,
                highres_images=highres_images,
                math_mode=self.config.surya.math_mode,
                detection_batch_size=self.config.surya.detector_batch_size,
                recognition_batch_size=self.config.surya.recognition_batch_size,
            )
        finally:
            for image in images:
                image.close()
            for highres_image in highres_images:
                highres_image.close()

    def recognize_crop_pdf_batch(self, batch: list[dict[str, Any]]) -> list[Any]:
        """Run Surya on formula crops embedded in a normal-size temp PDF."""

        from surya.input.load import load_from_file
        from surya.settings import settings

        recognition_predictor, detection_predictor = self.predictors()
        with tempfile.TemporaryDirectory(prefix="pdf-extract-math-crops-") as tmp_dir:
            pdf_path = Path(tmp_dir) / "crops.pdf"
            write_crop_batch_pdf(
                batch,
                pdf_path=pdf_path,
                image_dpi=self.config.docling.crop_pdf_dpi,
            )
            page_range = list(range(len(batch)))
            images, _ = load_from_file(str(pdf_path), page_range=page_range)
            highres_images, _ = load_from_file(
                str(pdf_path),
                page_range=page_range,
                dpi=settings.IMAGE_DPI_HIGHRES,
            )
            try:
                return recognition_predictor(
                    images,
                    task_names=[self.task_names.ocr_with_boxes] * len(images),
                    det_predictor=detection_predictor,
                    highres_images=highres_images,
                    math_mode=self.config.surya.math_mode,
                    detection_batch_size=self.config.surya.detector_batch_size,
                    recognition_batch_size=self.config.surya.recognition_batch_size,
                )
            finally:
                for image in images:
                    image.close()
                for highres_image in highres_images:
                    highres_image.close()

    def recognize_pdf_pages(self, pdf_path: Path, page_indexes: list[int]) -> tuple[list[dict[str, Any]], dict[str, float]]:
        """Run Surya on full PDF pages and return serialized predictions."""

        from surya.input.load import load_from_file
        from surya.settings import settings

        recognition_predictor, detection_predictor = self.predictors()
        timings: dict[str, float] = {}

        load_start = time.monotonic()
        images, _ = load_from_file(str(pdf_path), page_range=page_indexes)
        timings["lowres_load_seconds"] = time.monotonic() - load_start

        load_start = time.monotonic()
        highres_images, _ = load_from_file(
            str(pdf_path),
            page_range=page_indexes,
            dpi=settings.IMAGE_DPI_HIGHRES,
        )
        timings["highres_load_seconds"] = time.monotonic() - load_start

        try:
            synchronize_gpu()
            predict_start = time.monotonic()
            predictions = recognition_predictor(
                images,
                task_names=[self.task_names.ocr_with_boxes] * len(images),
                det_predictor=detection_predictor,
                highres_images=highres_images,
                math_mode=self.config.surya.math_mode,
                detection_batch_size=self.config.surya.detector_batch_size,
                recognition_batch_size=self.config.surya.recognition_batch_size,
            )
            synchronize_gpu()
            timings["prediction_seconds"] = time.monotonic() - predict_start

            serialize_start = time.monotonic()
            serialized_predictions = [
                serialize_surya_prediction(prediction)
                for prediction in predictions
            ]
            timings["serialization_seconds"] = time.monotonic() - serialize_start
            return serialized_predictions, timings
        finally:
            for image in images:
                image.close()
            for highres_image in highres_images:
                highres_image.close()
            if "predictions" in locals():
                del predictions
            timings["cleanup_seconds"] = cleanup_gpu_memory_seconds()


class SuryaCropRecognizer:
    """Recognize Docling-routed crops with shared Surya models."""

    def __init__(self, config: ExtractConfig | None = None) -> None:
        self.config = config or ExtractConfig()

    @staticmethod
    def candidate_input_mode(candidate: dict[str, Any]) -> str:
        """Use temp PDFs for formula zones and direct images for text crops."""

        if candidate.get("reason") == "docling_formula_cluster_zone":
            return "pdf"
        return "image"

    def recognize(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Run Surya on prepared crop candidates, mutating candidates with results."""

        crop_candidates = [candidate for candidate in candidates if candidate.get("_surya_image")]
        if not crop_candidates:
            return []

        batch_records: list[dict[str, Any]] = []
        with SuryaSession(self.config) as session:
            batch_index = 0
            grouped_candidates = [
                (
                    mode,
                    [
                        candidate
                        for candidate in crop_candidates
                        if self.candidate_input_mode(candidate) == mode
                    ],
                )
                for mode in ("image", "pdf")
            ]
            for input_mode, mode_candidates in grouped_candidates:
                if not mode_candidates:
                    continue
                for batch in chunk_list(mode_candidates, self.config.surya.crop_batch_size):
                    batch_index += 1
                    try:
                        start = time.monotonic()
                        if input_mode == "pdf":
                            predictions = session.recognize_crop_pdf_batch(batch)
                        else:
                            predictions = session.recognize_images(batch)
                        predict_seconds = time.monotonic() - start

                        for candidate, prediction in zip(batch, predictions):
                            candidate["surya"] = serialize_surya_prediction(prediction)
                            candidate["surya_input_mode"] = input_mode
                            candidate["surya_batch_index"] = batch_index
                            candidate["surya_model_seconds"] = round(
                                getattr(session, "model_seconds", 0.0),
                                3,
                            )
                            candidate["surya_batch_predict_seconds"] = round(
                                predict_seconds,
                                3,
                            )

                        batch_records.append(
                            {
                                "batch_index": batch_index,
                                "candidate_count": len(batch),
                                "candidate_ids": [candidate["candidate_id"] for candidate in batch],
                                "input_mode": input_mode,
                                "predict_seconds": round(predict_seconds, 3),
                            }
                        )
                    finally:
                        cleanup_gpu_memory()
        return batch_records


class SuryaFullPagePipeline:
    """Run full-page Surya OCR without Docling."""

    def __init__(self, config: ExtractConfig | None = None) -> None:
        self.config = config or ExtractConfig()

    def run(self, request: RunRequest) -> RunResult:
        self.require_gpu()
        page_count = self.page_count(request.input_pdf)
        page_indexes = parse_page_selection(request.pages, page_count)
        chunks = chunk_list(page_indexes, self.config.surya.page_chunk_size)
        print(
            f"[plan] {len(page_indexes)} pages in {len(chunks)} chunks of up to "
            f"{self.config.surya.page_chunk_size} pages",
            flush=True,
        )

        all_predictions: list[dict[str, Any]] = []
        chunk_records: list[dict[str, Any]] = []
        with SuryaSession(self.config) as session:
            for chunk in chunks:
                predictions, records = self.run_chunk_with_retry(
                    session=session,
                    pdf_path=request.input_pdf,
                    page_indexes=chunk,
                )
                all_predictions.extend(predictions)
                chunk_records.extend(records)

        if request.markdown_out is not None:
            markdown = predictions_to_markdown(all_predictions, page_indexes)
            request.markdown_out.parent.mkdir(parents=True, exist_ok=True)
            request.markdown_out.write_text(markdown.rstrip() + "\n", encoding="utf-8")
            print(f"Wrote Markdown: {request.markdown_out}", flush=True)

        rewrite_summary = None
        if request.pdf_out is not None:
            from .pdf_rewrite import FullPageSuryaPdfRewriter

            predictions_by_page = dict(zip(page_indexes, all_predictions))
            rewrite_summary = FullPageSuryaPdfRewriter(
                input_pdf=request.input_pdf,
                output_pdf=request.pdf_out,
                predictions_by_page=predictions_by_page,
                config=self.config,
            ).rewrite(policy=request.rewrite_policy)
            print(f"Wrote OCR PDF: {request.pdf_out}", flush=True)

        report = {
            "workflow": "surya-full",
            "source": str(request.input_pdf),
            "page_count": page_count,
            "pages": [page_index + 1 for page_index in page_indexes],
            "chunk_pages": self.config.surya.page_chunk_size,
            "math_mode": self.config.surya.math_mode,
            "chunks": chunk_records,
            "rewrite_summary": (
                {
                    "output_pdf": rewrite_summary.output_pdf,
                    "page_actions": rewrite_summary.page_actions,
                    "page_classes": rewrite_summary.page_classes,
                }
                if rewrite_summary
                else None
            ),
        }
        if request.json_out is not None:
            payload = {
                "source": str(request.input_pdf),
                "workflow": "surya-full",
                "page_count": page_count,
                "pages": [page_index + 1 for page_index in page_indexes],
                "predictions": all_predictions,
                "report": report,
            }
            request.json_out.parent.mkdir(parents=True, exist_ok=True)
            request.json_out.write_text(
                json_dumps(payload),
                encoding="utf-8",
            )
            print(f"Wrote JSON: {request.json_out}", flush=True)

        return RunResult(
            markdown_out=request.markdown_out,
            pdf_out=request.pdf_out,
            json_out=request.json_out,
            report=report,
        )

    @staticmethod
    def page_count(pdf_path: Path) -> int:
        """Return PDF page count."""

        from pypdf import PdfReader

        return len(PdfReader(pdf_path).pages)

    @staticmethod
    def require_gpu() -> None:
        """Fail rather than silently running Surya on CPU."""

        try:
            import torch
        except Exception as exc:
            raise RuntimeError("PyTorch is required for full-page Surya OCR.") from exc
        if not torch.cuda.is_available():
            raise RuntimeError(
                "PyTorch does not see a CUDA/ROCm GPU in this shell. Run from the elevated shell."
            )

    def run_chunk_with_retry(
        self,
        session: SuryaSession,
        pdf_path: Path,
        page_indexes: list[int],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Run one page chunk, retrying OOM failures as single pages."""

        start = time.monotonic()
        print(
            f"[surya] pages {page_labels(page_indexes)}: "
            f"recognition_batch_size={self.config.surya.recognition_batch_size}",
            flush=True,
        )
        try:
            predictions, timings = session.recognize_pdf_pages(pdf_path, page_indexes)
        except RuntimeError as error:
            cleanup_gpu_memory()
            if len(page_indexes) == 1 or not is_oom_error(error):
                raise
            print(
                f"[surya] pages {page_labels(page_indexes)}: OOM, retrying as single pages",
                flush=True,
            )
            combined_predictions: list[dict[str, Any]] = []
            combined_records: list[dict[str, Any]] = []
            for page_index in page_indexes:
                page_predictions, page_records = self.run_chunk_with_retry(
                    session=session,
                    pdf_path=pdf_path,
                    page_indexes=[page_index],
                )
                combined_predictions.extend(page_predictions)
                combined_records.extend(page_records)
            return combined_predictions, combined_records

        seconds = time.monotonic() - start
        print(
            f"[surya] pages {page_labels(page_indexes)}: completed in {seconds:.1f}s "
            f"(load {timings['lowres_load_seconds']:.1f}s/"
            f"{timings['highres_load_seconds']:.1f}s, "
            f"predict {timings['prediction_seconds']:.1f}s, "
            f"serialize {timings['serialization_seconds']:.1f}s, "
            f"cleanup {timings['cleanup_seconds']:.1f}s)",
            flush=True,
        )
        return predictions, [
            {
                "page_indexes": page_indexes,
                "page_labels": [page_index + 1 for page_index in page_indexes],
                "seconds": round(seconds, 3),
                "timings": {
                    key: round(value, 3)
                    for key, value in timings.items()
                },
            }
        ]
