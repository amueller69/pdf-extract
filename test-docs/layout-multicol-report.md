# Regional Intake Bulletin

Layout Stress Test for Multi-column Parsing

Document AI Evaluation Team

June 2026

Document purpose. This fixture contains two-column body text, running headers, page numbers, inline charts, a full-width table, a narrow callout box, and footnotes. It is designed to test whether a layout pipeline preserves reading order when visual objects interrupt ordinary prose.

## Morning Intake

The regional intake desk receives packets from three sources: secure upload, mailroom scan, and partner batch delivery. Each source has a different failure mode. Uploads are usually complete but often include duplicate supporting pages. Mailroom scans are the most likely to contain skewed images, stapled receipts, or blank separator sheets. Partner batches tend to be clean, but they arrive late in the day and create a surge just before the quality review window closes.

The first-pass reviewer labels each packet with a case type, a source code, and a confidence flag. Confidence is not a judgment about the legal merit of the packet. It is a signal that tells downstream orchestration whether the packet can be routed automatically or should be held for a human review queue. Reviewers are told to prefer a conservative hold when the cover sheet and the attachments disagree.

**Figure 1. Weekly intake queue**

| Day | Packets |
| --- | ---: |
| Mon | 42 |
| Tue | 55 |
| Wed | 48 |
| Thu | 68 |
| Fri | 61 |

Bars show document packets waiting for first-pass classification.

When the queue rises above sixty packets, the desk changes its routing pattern. Straightforward renewals are released immediately, while mixed packets are grouped by source. The chart above interrupts the text deliberately: a correct reading order should finish the paragraph before the chart, include the figure title and labels, and then resume here.

## Column Balancing

Column balancing is especially important in bulletins that combine dense prose with operational objects. A reader expects the left column to continue before the right column unless a full-width object establishes a new section break. The test therefore places a table on the next page that spans both columns. Systems that only sort by vertical position may interleave the table with the wrong column.

**Reviewer note**

The gray boxes are not advertisements. They are operational callouts and should be preserved as text blocks, preferably after the paragraph that introduces them.

The desk also tracks the distance between receipt time and validation time. That interval is short when a packet has a clear cover sheet and a predictable attachment sequence. It grows when a reviewer must inspect the page image rather than rely on recognized text. The layout engine should not drop the small labels that explain why a packet was held.

## Afternoon Review

The afternoon review begins with a short standup. Supervisors compare queue length, age of oldest packet, and number of exceptions. This paragraph includes a footnote because small superscripts often sit close to punctuation in multi-column layouts.[^1] The footnote text appears at the bottom of the page and should be associated with this sentence.

For partner batches, the most common issue is inconsistent naming. A cover sheet may identify a party as "Lake Street Holdings" while an attachment says "Lake St. Holdings LLC." The reviewer records the mismatch but does not change the canonical name unless another source confirms the update. This policy keeps the automation layer from overwriting stable identifiers with noisy OCR output.

## Table Placement

Table 1 is a full-width object. It is intentionally positioned at the top of a page, separate from the column that introduces it. The expected markdown should record the table after the afternoon review material that discusses routing, even if the rendering engine floats it visually.

**Table 1. Full-width routing summary**

| Source | Daily packets | Auto-routed | Held | Primary hold reason |
| --- | ---: | ---: | ---: | --- |
| Secure upload | 184 | 151 | 33 | Duplicate attachments or conflicting cover sheet values |
| Mailroom scan | 96 | 58 | 38 | Skewed image, missing signature, or low contrast receipt |
| Partner batch | 127 | 102 | 25 | Late arrival, naming mismatch, or batch manifest variance |
| Field office | 44 | 28 | 16 | Handwritten amendment or missing identity page |

After the summary table, reviewers sample a small number of completed packets. They compare the extracted fields with the original page image and mark three categories: correct, recoverable, and failed. Correct fields require no intervention. Recoverable fields need a small edit, such as normalizing a date. Failed fields require a reviewer to re-open the source packet.

The sampling process is deliberately boring. Its value comes from consistency. If the sample changes every week, the trend line reflects sampling noise rather than process improvement. The same case types, sources, and quality bands are therefore represented in each sample.

## End-of-day Closeout

Closeout starts when no new partner batches are expected. The supervisor exports the exception register, checks whether any packet has exceeded the service target, and sends a short note to the next shift. The note includes the oldest packet identifier, the count of high-priority holds, and a description of anything unusual.

**Figure 2. Exception mix at closeout**

| Category | Share |
| --- | ---: |
| Missing ID | 33% |
| Bad date | 19% |
| Low scan | 15% |
| Duplicate | 11% |
| Other | 22% |

The chart is intentionally placed after the surrounding paragraph.

The final chart appears near the bottom of the column. It tests whether the parser can capture chart labels after a paragraph rather than treating them as a footer. A system that discards low-position objects may lose the exception categories even though they contain the most useful operational signal.

The bulletin ends with a short acknowledgement. This document is synthetic and does not contain real client data. Names, counts, and percentages were chosen only to exercise layout behavior in an OCR orchestration pipeline.

[^1]: The service target in this synthetic document is four business hours from first receipt to validation.
