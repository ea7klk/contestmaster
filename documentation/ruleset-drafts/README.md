# Importable contest ruleset starter drafts

Each JSON file in this folder is a separate schema-version-2 draft. In the Ruleset composer choose **Import JSON draft** and select one file. After import, validate and review the draft before saving it as a version.

These are teaching and configuration starters, not official or complete implementations of the sponsor's rules. Check the linked official rules for the contest edition you intend to run. In particular, confirm dates, submission deadline, categories, exchange variants, mode/band eligibility, multipliers, point values, penalties, and adjudication. Contestmaster now has reusable rules for entrant-relative geography, distance points, conditional/distinct-count bonuses, independent multiplier totals, and fixed-interval scoring sessions; these examples remain partial and must not be activated or published without sponsor review. The files summarize no contest rule text; each points to its sponsor's rules page.

Category dimensions and choices support optional `description` text. Use it to record the sponsor's precise qualification for the specific edition, especially power thresholds and the power measurement point. When a power description is omitted, the generated public overview assumes QRP up to 5 W, Low Power up to 100 W, and High Power up to the legal limit. Sponsor-specific descriptions and published rules take precedence.

The CQ WW drafts calculate `(CQ-zone multipliers + country multipliers) × QSO points` by referencing the two configured multiplier rules independently. The RSGB example configures commenced-kilometer scoring from six-character locator cell centers, a same-cell value, and fixed UTC sessions that restart duplicate identity and sent serials. It is deliberately limited; it is not a complete RSGB log profile or a reproduction of cumulative activity scheduling. Other examples retain a simple integer score formula baseline. All files contain reusable rules only: enter start/end times, periodicity, and the log-submission cutoff in contest configuration. A source edition is included in every file to make the provenance visible in the composer.

Cabrillo drafts explicitly configure each required QSO column (`frequency`, `mode`, `date`, `time`, and the sent/received station and exchange fields) exactly once, and map their configured categories from Cabrillo header values. WWROF allows supported contest templates to order those fields differently; the ruleset's order is used to interpret and generate the example. A final optional `transmitter` field is supported. Omitted or incomplete columns fail API ruleset validation. Every enabled import format must map every required category dimension. The API validation endpoint reports incompatible columns or incomplete category mappings before a version can be saved; older immutable versions remain readable for existing contest views. The public contest page uses the saved ruleset mappings to generate its two-QSO sample. It translates shared catalog modes to Cabrillo QSO tokens, for example SSB to `PH`, RTTY to `RY`, and FT8/FT4 to `DG`. It does not invent missing mappings or substitute fields absent from the ruleset.

## Drafts

| Mode family | Contest | Draft |
| --- | --- | --- |
| Digital | ARRL International Digital Contest | [arrl-international-digital.json](arrl-international-digital.json) |
| Digital | World Wide Digi DX Contest | [world-wide-digi-dx.json](world-wide-digi-dx.json) |
| RTTY | CQ WW RTTY DX Contest | [cq-ww-rtty.json](cq-ww-rtty.json) |
| RTTY | ARRL RTTY Roundup | [arrl-rtty-roundup.json](arrl-rtty-roundup.json) |
| FT8 | ARI FT8 Activity Contest | [ari-ft8-activity.json](ari-ft8-activity.json) |
| FT8 | VHF-UHF FT8 Activity | [vhf-uhf-ft8-activity.json](vhf-uhf-ft8-activity.json) |
| FT4 | RSGB FT4 International Activity Day | [rsgb-ft4-international-activity-day.json](rsgb-ft4-international-activity-day.json) |
| FT4 | Africa FT4 DX Contest | [sarl-africa-ft4-dx.json](sarl-africa-ft4-dx.json) |
| CW | CQ WW DX Contest (CW) | [cq-ww-cw.json](cq-ww-cw.json) |
| CW | ARRL November Sweepstakes (CW) | [arrl-november-sweepstakes-cw.json](arrl-november-sweepstakes-cw.json) |
| SSB | CQ WW DX Contest (SSB) | [cq-ww-ssb.json](cq-ww-ssb.json) |
| SSB | ARRL November Sweepstakes (Phone) | [arrl-november-sweepstakes-phone.json](arrl-november-sweepstakes-phone.json) |
| VHF/UHF | RSGB VHF/UHF/SHF General Rules distance and fixed-session example | [rsgb-vhf-general-distance-sessions.json](rsgb-vhf-general-distance-sessions.json) |
| CW | SARL ZS2 QSO Party (ADIF, outside-entrant scoring profile) | [sarl-zs2-qso-party-adif.json](sarl-zs2-qso-party-adif.json) |

The ARI FT8 Activity and VHF-UHF FT8 Activity drafts enable ADI/ADIF because their published rules require ADIF submissions. The RSGB FT4 International Activity Day draft enables both ADI/ADIF and Cabrillo, matching its published alternatives. The SARL ZS2 example is a limited outside-entrant profile using conditional points and explicit ADIF sent/received exchange-tag mappings; it is not a complete event ruleset. Other draft format choices are starters and must be checked against the linked contest edition before use.

## Validate all drafts against the current backend schema

Run this from the repository root:

```sh
.venv/bin/python - <<'PY'
import json
from pathlib import Path
from backend.app.rulesets.validation import validate_ruleset

for path in sorted(Path("documentation/ruleset-drafts").glob("*.json")):
    ruleset = validate_ruleset(json.loads(path.read_text()))
    print(f"{path.name}: valid ({len(ruleset.rules)} configured rules)")
PY
```

A successful schema check confirms that the current composer/backend can load the draft structure; it does not verify that the values implement the sponsor's full rulebook.

The schema-version-2 bonus rule uses the presence of `evidence_key` to indicate that an evidence declaration is required. Older drafts that also include `evidence_required` are accepted only when the boolean agrees with the key's presence; import removes that redundant field and exports omit it. The supplied starter drafts are schema version 2: event dates, recurrence, and cutoff timestamps belong to contest configuration and are absent from reusable rulesets. Legacy version 1 drafts can be imported in the composer, which removes those legacy settings before export.

The Vue import flow is covered by a test that loads every draft through the file-input workflow:

```sh
cd frontend
npm test -- --run src/views/RulesetDraftSamples.test.ts
```
