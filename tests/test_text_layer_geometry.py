from types import SimpleNamespace
import unittest

from docling_core.types.doc.base import CoordOrigin
from docling_core.types.doc.page import BoundingRectangle

from pdfextract.docling_pipeline import (
    build_hybrid_ocr_lines,
    cell_is_replaced_by_surya,
    page_layout_text_cells,
)
from pdfextract.models import BBox
from pdfextract.pdf_rewrite import FullPageSuryaPdfRewriter, PdfPageClassifier


def rectangle(x0, y0, x1, y1, origin=CoordOrigin.TOPLEFT):
    return BoundingRectangle(
        r_x0=x0,
        r_y0=y0,
        r_x1=x1,
        r_y1=y0,
        r_x2=x1,
        r_y2=y1,
        r_x3=x0,
        r_y3=y1,
        coord_origin=origin,
    )


class TextLayerGeometryTests(unittest.TestCase):
    def test_docling_cells_become_individual_positioned_records(self):
        cells = [
            SimpleNamespace(
                text="first line",
                rect=rectangle(20, 30, 120, 40),
                confidence=0.9,
                from_ocr=True,
                index=1,
            ),
            SimpleNamespace(
                text="second line",
                rect=rectangle(20, 45, 130, 55),
                confidence=0.8,
                from_ocr=True,
                index=2,
            ),
        ]
        page = SimpleNamespace(
            page_no=1,
            size=SimpleNamespace(width=200.0, height=300.0),
            cells=cells,
        )

        lines = build_hybrid_ocr_lines(SimpleNamespace(pages=[page]), [])

        self.assertEqual([line.text for line in lines], ["first line", "second line"])
        self.assertEqual(lines[0].bbox, BBox(20.0, 30.0, 120.0, 40.0))
        self.assertEqual(lines[1].metadata["source"], "docling_text_cell")

    def test_bottom_left_cells_are_converted_to_top_left_coordinates(self):
        cell = SimpleNamespace(
            text="converted",
            rect=rectangle(20, 260, 120, 270, CoordOrigin.BOTTOMLEFT),
            confidence=1.0,
            from_ocr=False,
            index=1,
        )
        page = SimpleNamespace(
            page_no=1,
            size=SimpleNamespace(width=200.0, height=300.0),
            cells=[cell],
        )

        line = build_hybrid_ocr_lines(SimpleNamespace(pages=[page]), [])[0]

        self.assertEqual(line.bbox, BBox(20.0, 30.0, 120.0, 40.0))

    def test_cells_mostly_inside_surya_regions_are_replaced(self):
        self.assertTrue(
            cell_is_replaced_by_surya(
                BBox(20, 20, 80, 30),
                [BBox(15, 15, 85, 35)],
            )
        )
        self.assertFalse(
            cell_is_replaced_by_surya(
                BBox(20, 20, 80, 30),
                [BBox(75, 15, 85, 35)],
            )
        )

    def test_layout_cells_include_nested_and_unassigned_cells_once(self):
        first = SimpleNamespace(
            text="cluster line",
            rect=rectangle(20, 30, 120, 40),
            confidence=1.0,
            from_ocr=True,
            index=1,
        )
        second = SimpleNamespace(
            text="unassigned line",
            rect=rectangle(20, 45, 130, 55),
            confidence=1.0,
            from_ocr=True,
            index=2,
        )
        child = SimpleNamespace(cells=[first], children=[])
        root = SimpleNamespace(cells=[], children=[child])
        page = SimpleNamespace(
            predictions=SimpleNamespace(
                layout=SimpleNamespace(clusters=[root]),
            ),
            cells=[first, second],
        )

        cells = page_layout_text_cells(page)

        self.assertEqual([cell.text for cell in cells], ["cluster line", "unassigned line"])

    def test_font_fitting_never_expands_beyond_bbox_width(self):
        rewriter = object.__new__(FullPageSuryaPdfRewriter)
        rewriter.fitz = __import__("fitz")
        rewriter.config = __import__(
            "pdfextract.config",
            fromlist=["ExtractConfig"],
        ).ExtractConfig()

        font_size = rewriter.fit_hidden_font_size(
            "a long line that must fit",
            base_font_size=10.0,
            available_width=20.0,
        )
        rendered_width = rewriter.fitz.get_text_length(
            "a long line that must fit",
            fontname="helv",
            fontsize=font_size,
        )

        self.assertLessEqual(rendered_width, 20.001)

    def test_image_dominant_page_with_visible_text_preserves_original_page(self):
        class_name, action = PdfPageClassifier.auto_classification(
            visible_chars=100,
            hidden_chars=0,
            image_coverage=1.0,
            full_page_image=True,
        )

        self.assertEqual(class_name, "scanned-no-ocr")
        self.assertEqual(action, "add-hidden-text")

    def test_image_dominant_page_with_hidden_text_replaces_only_hidden_layer(self):
        class_name, action = PdfPageClassifier.auto_classification(
            visible_chars=100,
            hidden_chars=100,
            image_coverage=1.0,
            full_page_image=True,
        )

        self.assertEqual(class_name, "scanned-hidden-ocr")
        self.assertEqual(action, "replace-hidden")


if __name__ == "__main__":
    unittest.main()
