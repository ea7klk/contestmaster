# N1MM built-in profile extraction

This directory is the working area for translating built-in N1MM Logger+ contest profiles into Contestmaster ruleset drafts. The target is update **1.0.11466**. The extraction is static; neither the installer nor the logger is executed, and vendor binaries or decompiled method bodies are not checked into Contestmaster.

## Current status

[`profile-inventory.json`](profile-inventory.json) maps all **263 factory dispatch keys** to **142 handler classes**. It also records decompiled source method locations and selected literal setup values for review. These records are source inventory only: **there are no N1MM-derived, importable ruleset JSON files in this directory yet**. Do not import the inventory as contest rules or use it to score a contest.

N1MM handlers are executable code and some shared handlers branch on the selected profile or entrant. The extracted default metadata alone is insufficient to reconstruct their exchange validation, duplicate scopes, multiplier rules, scoring formulas, and format behavior. Each profile must be translated and checked for fidelity. Sponsor-published rules remain authoritative for a real contest edition. Profiles that cannot be faithfully represented must be listed in [`unconverted-profiles.md`](unconverted-profiles.md), with their concrete Contestmaster functionality gaps.

## Source provenance

- Official update page and download: [N1MM Logger+ Update 1.0.11466](https://n1mmwp.hamdocs.com/mmfiles/n1mm-logger-update-1-0-11466-october-13-2026/).
- Downloaded archive SHA-256: `9586bb1d2b9de9b7a6a03f0526305419fe85ce610023ff9d65cc2d2e46eac7c0`.
- The source binary was obtained using the page's download form. It is kept outside the repository and is not redistributed.
- The code extraction uses ILSpy command-line **9.1.0.7988** against `N1MMLogger.net.exe` and its matching PDB. The extraction does not execute the assembly.
- The binary and method inventory are described in the user-provided `/root/n1mm/n1mm-handlers.md` and `/root/n1mm/n1mm-diff.md`; those files are not assumed to be available in another checkout.

## Rebuild the inventory

Install .NET 8 and ILSpy `ilspycmd` 9.1.0.7988 locally, download the official update from its website, and extract the assembly and matching PDB with a static archive tool. Decompile to a temporary directory:

```sh
ilspycmd -p -o /tmp/n1mm-decompiled /path/to/N1MM-Logger-Update-1.0.11466.exe
python3 documentation/ruleset-n1mm-builtin/extract_inventory.py \
  --decompiled-source /tmp/n1mm-decompiled \
  --output documentation/ruleset-n1mm-builtin/profile-inventory.json
```

The tool records dispatch keys, handler names, source method line references, and selected literal setup metadata. It intentionally does not copy method bodies or claim that literals alone comprise the contest rules.

## Output layout

- `profile-inventory.json` — complete key-to-handler inventory and extraction references.
- `rulesets/` — only fidelity-reviewed Contestmaster import drafts; each draft must retain source provenance and pass the current schema and semantic validation.
- `blocked/` — structured analysis JSON for profiles whose behavior cannot yet be represented safely.
- `unconverted-profiles.md` — human-readable list of blocked profiles, their behavior, and the specific missing Contestmaster capability or reference facts.

The last three deliverables are still in progress. An empty/missing output folder does not mean a profile is supported.

## Related issues

Tracked under parent [#398](https://github.com/ea7klk/contestmaster/issues/398), with extraction, conversion, gap inventory, and validation children [#399–#405](https://github.com/ea7klk/contestmaster/issues/399).
