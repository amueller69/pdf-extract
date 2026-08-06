# Benefits Enrollment Audit Memo

Single-column layout with charts, tables, footnotes, and headers

Prepared for OCR orchestration testing

June 2026

**Chart A. Enrollment calls by channel**

| Channel | Count |
| --- | ---: |
| Phone | 320 |
| Portal | 245 |
| Mail | 110 |
| Office visit | 72 |

Values count calls or visits logged during the sample week.

## Overview

This memo uses a conventional single-column page structure. The chart at the top is placed before the first section so that a parser must decide whether it belongs to the title block, the following section, or a separate figure region. The intended reading order is title, subtitle, preparation line, chart, chart note, and then the overview text.

The sample office reviews enrollment records for four programs. Most records arrive through a portal, but the oldest records often begin as phone calls. Staff members convert those calls into a structured record after confirming identity, address, and program type. The audit asks whether the conversion preserves the applicant's stated intent and whether attachments are labeled in a way that downstream systems can use.

The memo contains ordinary prose, footnotes, a chart that interrupts text, and a long table. It also has running headers and page numbers. Those running elements should not be repeated as body paragraphs in the ground truth, although a layout model may expose them as page header and footer regions.

## Sampling Rules

The sample is drawn every Friday afternoon. Records are grouped by channel, then sampled within each channel so that no single intake path dominates the review. A supervisor may add a small number of directed records when a policy change has just taken effect.[^1]

The reviewer starts with the final structured record and works backward to the source packet. This direction is intentional. It reveals whether the current record can be justified from the available evidence. If a field appears in the record but cannot be traced to the packet, the field is marked unsupported even when it appears plausible.

## Interruption Case

The following chart appears in the middle of a paragraph sequence. It should be captured between the sentence that introduces it and the sentence that resumes the discussion. Some OCR systems treat charts as decorative because they contain only short labels and numbers. In this fixture, those labels are the most important evidence for the paragraph.

**Chart B. Average resolution time**

| Work item | Average resolution time |
| --- | ---: |
| Identity check | 1.2 days |
| Income review | 2.8 days |
| Address update | 0.9 days |
| Appeal packet | 3.6 days |

The resolution time pattern drives staffing decisions. Appeal packets take the longest because they require two independent checks and a final notice. Income review is shorter, but it creates more rework because the packet may contain pay stubs, benefit letters, and handwritten explanations. Identity checks are usually simple unless the scan quality is poor.

## Detailed Findings

The table below uses repeated row structure, narrow numeric columns, and a text-heavy notes column. It is placed after the chart so that extraction can be evaluated for both object order and cell order. The values are synthetic but internally consistent.

**Table 1. Weekly audit findings**

| Program | Reviewed | Correct | Rework | Notes |
| --- | ---: | ---: | ---: | --- |
| Nutrition | 42 | 35 | 7 | Most rework involved missing proof of address or a stale phone number. |
| Transit | 28 | 23 | 5 | Two records had attachments assigned to the wrong household member. |
| Health | 36 | 27 | 9 | Income evidence was present but split across several image-only pages. |
| Child care | 31 | 24 | 7 | The most common issue was an unsigned provider statement. |
| Housing | 25 | 20 | 5 | Reviewers found inconsistent apartment numbers in three packets. |

## Footer and Footnote Stress

The final page includes a short list, a small table, and another footnote. It exists mainly to test page headers, footers, and low-position text. Extraction should avoid merging the footer with the final paragraph.

- Records marked correct can proceed without manual correction.
- Records marked rework require a case note before release.
- Records marked unsupported must be returned to the intake supervisor.

The audit team also records whether the page image was readable. This is separate from record correctness. A record can be correct even when a scanned attachment is unpleasant to read, and a clean scan can still contain the wrong document. The distinction matters because OCR remediation and policy remediation belong to different teams.

**Table 2. Image readability sample**

| Readability band | Pages | Share |
| --- | ---: | ---: |
| Clear | 214 | 71% |
| Usable with zoom | 61 | 20% |
| Poor | 28 | 9% |

The recommended next step is to focus on income review packets because they combine the highest rework rate with a moderate scan-quality burden. The team should update attachment labels first, then revisit policy prompts if the next two weekly samples show the same pattern.[^2]

[^1]: Directed records are included in the audit count but excluded from trend comparisons.

[^2]: This recommendation is part of the synthetic fixture and is not based on real applicant data.
