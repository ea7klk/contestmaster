# N1MM profiles not yet converted

This list is being built from the exact N1MM 1.0.11466 handler implementation. It is intentionally marked **not yet assessed** until each key's score-relevant code paths have been traced. A profile must not be labeled “unconvertible” merely because conversion work has not yet been done; similarly, an artifact is not a complete ruleset just because it parses as JSON.

| Dispatch keys | Handler | Conversion status | Known Contestmaster gap or remaining analysis |
| --- | --- | --- | --- |
| All 263 keys in [`profile-inventory.json`](profile-inventory.json) | 142 handler classes | Not yet assessed | Need per-key extraction of exchange/category requirements, duplicate identity, multiplier source/scope, points, final formula, eligibility/workability, and output format. Shared handler branches must be distinguished per dispatch key. |

As each profile is reviewed, replace this summary row with one or more profile rows. Name the exact code behavior and missing Contestmaster fact, rule type, reference dataset, or log-format capability. Profiles blocked only on sponsor-edition verification must be distinguished from profiles requiring a new engine capability.

See the parent gap analysis and implementation tracking in [issue #398](https://github.com/ea7klk/contestmaster/issues/398), especially [#404](https://github.com/ea7klk/contestmaster/issues/404).
