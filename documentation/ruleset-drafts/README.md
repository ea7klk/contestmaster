# Importable contest ruleset starter drafts

Each JSON file in this folder is a separate schema-version-1 draft. In the Ruleset composer choose **Import JSON draft** and select one file. After import, validate and review the draft before saving it as a version.

These are teaching and configuration starters, not official or complete implementations of the sponsor's rules. Check the linked official rules for the contest edition you intend to run. In particular, confirm dates, submission deadline, categories, exchange variants, mode/band eligibility, multipliers, point values, penalties, and adjudication. Several contests have geographic or participant-specific conditions that the current rules engine cannot yet express. Do not activate or publish a contest from one of these examples without that review. The files summarize no contest rule text; each points to its sponsor's rules page.

The examples use a simple integer score formula as a valid baseline. It does not claim to reproduce each sponsor's official calculation. A source edition is included in every file to make the provenance visible in the composer.

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

The Vue import flow is covered by a test that loads every draft through the file-input workflow:

```sh
cd frontend
npm test -- --run src/views/RulesetDraftSamples.test.ts
```
