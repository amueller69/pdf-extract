"""Heuristic score for math-like OCR/raw text spans."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable


MATH_FONTS = {
    "CMMI", "CMSY", "CMEX", "MSAM", "MSBM", "EUFM", "EUSM",
    "TXMI", "TXSY", "PXMI", "PXSY", "CambriaMath", "STIXMath",
    "XitsMath", "Latin Modern Math", "AsanaMath", "MTMI", "MTSYN",
}

LATEX_RE = re.compile(r"\\(?:frac|sum|int|sqrt|alpha|beta|gamma|theta|lambda|mu|sigma|pi|infty|left|right)\b")
VAR_OP_RE = re.compile(r"[A-Za-zα-ωΑ-Ω0-9][\s]*(?:=|≈|≠|≤|≥|[+\-*/^_<>])[\s]*[A-Za-zα-ωΑ-Ω0-9(]")
FUNC_RE = re.compile(r"\b(?:sin|cos|tan|log|ln|exp|lim|Pr|Var|Cov|E)\s*[\[(]")
SUBSUP_RE = re.compile(r"(?:[A-Za-zα-ωΑ-Ω][_^][A-Za-z0-9]+|[A-Za-zα-ωΑ-Ω][⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉])")
MONEY_DATE_RE = re.compile(r"^\s*(?:\$?\d{1,4}(?:[.,/:-]\d{1,4})+|\$[\d,]+(?:\.\d+)?)\s*$")


def mathematics_score(text: str, font_names: Iterable[str] = ()) -> float:
    """Return 0..1 score that a text span is mathematical notation."""

    s = (text or "").strip()
    if not s:
        return 0.0

    score = 0.0
    compact = re.sub(r"\s+", "", s)

    if MONEY_DATE_RE.match(s):
        score -= 0.35
    if any(font in MATH_FONTS for font in font_names):
        score += 0.30
    if "$" in s or r"\(" in s or r"\[" in s or LATEX_RE.search(s):
        score += 0.45
    if VAR_OP_RE.search(s):
        score += 0.35
    if FUNC_RE.search(s):
        score += 0.20
    if SUBSUP_RE.search(s):
        score += 0.20

    math_symbols = sum(unicodedata.category(ch) == "Sm" for ch in s)
    greek = sum("\u0370" <= ch <= "\u03ff" for ch in s)
    one_char_tokens = len(re.findall(r"\b[A-Za-zα-ωΑ-Ω]\b", s))

    score += min(0.35, math_symbols * 0.08)
    score += min(0.25, greek * 0.06)
    score += min(0.20, one_char_tokens * 0.04)

    if len(compact) <= 2 and math_symbols == 0 and not greek:
        score -= 0.25
    if re.search(r"[A-Za-z]{8,}", compact) and math_symbols == 0:
        score -= 0.20

    return round(max(0.0, min(1.0, score)), 3)
