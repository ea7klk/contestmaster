# Sponsor rule facts, ranked by frequency

**Inventory reviewed:** 259 records from `sponsor-rule-samples.json`  
**Sorting:** descending count of records whose fact status is `stated`.

This is a summary of the observed rule facts, not the contest-family tags. Counts refer to inventory records, not independent rulebooks: 143 records are recurring sessions that reuse sponsor-published series rules. Shared facts and facts awaiting edition confirmation are shown separately and are not counted as explicit event-level facts.

## Rule-fact areas

| Rank | Rule-fact area | Explicitly stated | Generic/shared | Needs edition confirmation | What the records cover |
|---:|---|---:|---:|---:|---|
| 1 | Bands | 190 (73.4%) | 0 | 69 | HF, VHF, UHF and SHF bands; the most frequent specific bands are 144 MHz and 432 MHz. |
| 2 | Modes | 183 (70.7%) | 0 | 76 | FT8 and FM are frequent; many VHF rules permit a common CW/phone/FM/AM/MGM set. |
| 3 | Scoring and multipliers | 162 (62.5%) | 0 | 97 | Distance points, locator-square bonuses, QSO points, and multiplier formulas. |
| 4 | Duplicate policy | 157 (60.6%) | 17 | 85 | Per-band/session contact limits and band/mode/geographic repeat policies. |
| 5 | Exchange | 151 (58.3%) | 17 | 91 | Serial and locator exchanges, signal reports, and geographic values such as counties or sections. |
| 6 | Categories | 149 (57.5%) | 0 | 110 | Open/restricted/low-power sections, power classes, and participant or station classes. |
| 7 | Operating limits | 0 | 143 | 116 | The recurring-session rows identify short windows and possible series scoring generically; exact operating constraints need edition review. |
| 8 | Log submission | 0 | 143 | 116 | The recurring-session rows identify sponsor portal submission generically, with ADIF noted for FT8; exact accepted formats and deadlines need edition review. |

The `stated` label means the sample record contains a specific value or rule summary. It does not mean every contest in the same family follows that rule. `Generic/shared` identifies a family or common-rule summary that still needs to be matched to the individual event. `Needs edition confirmation` means the record intentionally does not assert a value.

## Most frequent concrete patterns

| Rank | Observed rule fact | Records | Evidence note |
|---:|---|---:|---|
| 1 | One scoring contact per station per band/session | 143 | Stated for recurring-session samples; verify the precise duplicate key on the applicable sponsor page. |
| 2 | Short session and possible best-eight series contribution | 143 | Generic shared series summary; not asserted as an exact rule for every event. |
| 3 | Open, restricted, and low-power sections | 119 | Stated category pattern in the VHF session samples. |
| 4 | Integer distance points plus a locator-square bonus | 119 | Combined from 71 session records with “plus” wording and 48 FT8 records with the same scoring components. |
| 5 | RS(T), session/date serial, and six-character locator | 95 | Stated exchange pattern in VHF activity contest sessions. |
| 6 | SSB, CW, FM, AM, JT6M, and FSK441 | 71 | Stated permitted-mode set in VHF activity sessions. |
| 7 | FT8; report and four-character locator, no serial | 48 | Stated pattern for the 2-hour and 4-hour FT8 activity sessions. |
| 8 | 144 MHz and 432 MHz | 48 each | Most frequent specific band values in the inventory. |
| 9 | FM; 10 W and 50 W sections | 24 | Stated pattern in the FM activity contest sessions. |
| 10 | One integer point per kilometre | 24 | Stated FM distance-scoring rule. |

## Data limits

- Source facts are paraphrased and linked in the [main body of knowledge](README.md); sponsor rules for the selected edition remain authoritative.
- The source inventory contains 116 named rule profiles and 143 recurring-session records. Repeated series entries increase record counts, so use the `sample_kind` field when comparing independent event profiles.
- Many named contest profiles deliberately mark details as needing edition confirmation. Their counts should not be read as proof that the rules were fully adjudicated from every current edition.
- This ranking is descriptive. It does not define Contestmaster defaults or claim that a more frequent rule deserves higher implementation priority.
