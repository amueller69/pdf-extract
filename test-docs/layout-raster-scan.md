# Harbor Clinic Intake Packet

Image-only PDF source for OCR testing

Packet ID: HC-2047-06

Date received: 2026-06-03

## Page 1: Cover Sheet

**Name:** blank

**Date of birth:** blank

**Primary phone:** blank

**Preferred language:** blank

**Visit reason:** [x] New patient [ ] Renewal [ ] Records request [ ] Billing question

**Referral source:** [ ] Employer [x] Community clinic [ ] School [ ] Other

**Staff note**

The applicant arrived with a folded paper referral and two copied identity documents. The copy of the back side of the card is faint but readable. The handwritten phone number should be checked against the typed appointment record before release.

### Attachment checklist

| Attachment | Present |
| --- | --- |
| Photo ID front | yes |
| Photo ID back | yes |
| Referral letter | yes |
| Insurance card | no |
| Consent form | no |
| Address proof | yes |

### Small print notice

This synthetic packet contains blank lines, checkboxes, boxed notes, and low-position footer text. The final PDF should be rasterized so that no selectable text layer remains. Ground truth should preserve the visible words, checkbox states, and table values.

## Page 2: Triage Log

**Table 1. Vitals and triage observations**

| Time | Staff | Priority | Observation |
| --- | --- | --- | --- |
| 08:14 | R. Patel | Routine | Packet opened; cover sheet complete; referral attached. |
| 08:22 | M. Chen | Watch | Address proof copied at low contrast; request rescan if rejected. |
| 08:39 | R. Patel | Routine | Language preference confirmed by phone. |
| 09:05 | L. Ortiz | Hold | Insurance card missing; applicant will bring card at appointment. |

**Chart 1. Triage priority counts**

| Priority | Count |
| --- | ---: |
| Routine | 2 |
| Watch | 1 |
| Hold | 1 |

The triage chart is deliberately simple. It is included to test whether OCR orchestration retains numeric chart labels when the PDF has only page images. A layout system should not assume that simple bars are decorative.

**Handwritten-style note:** call back after 2 p.m.; voicemail okay; ask for updated insurance card.

## Page 3: Release Review

**Reviewer:** A. Morris

**Review date:** 2026-06-04

**Release decision:** [ ] Release now [x] Hold for missing card [ ] Return packet

**Table 2. Field verification**

| Field | Status | Comment |
| --- | --- | --- |
| Name | Verified | Matches referral and identity page. |
| Date of birth | Verified | Typed value agrees with copied card. |
| Phone | Needs check | Handwritten digit may be 3 or 8. |
| Insurance | Missing | Applicant says card will be available at appointment. |
| Address | Verified | Utility bill image is low contrast but readable. |

**Final note**

Do not auto-release this packet until the insurance card is attached. If the card is received before the appointment, update the status field and keep the original triage note in the record.

The document is synthetic. Names, times, and packet numbers are invented for OCR testing.
