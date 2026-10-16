# Contestmaster web design direction

This document records the approved visual and interaction direction for the Vue application and keeps the other mockups for reference.

## Reference review: POTA.app

Reviewed on 2026-10-16. The live POTA site is a JavaScript application, so its public page is not fully represented by text-only inspection. POTA's own help material and the indexed live page show a compact set of section links for spots, activations, maps, park lists, and leaderboards; a callsign/park search; a filter-first active feed; and more than one way to view results. Its hunter guide describes a three-bar menu with view preferences such as a table view and a low-light mode. See [POTA.app](https://pota.app/), the [POTA.app help index](https://docs.pota.app/pota_app/index.html), and the [POTA Hunter Guide](https://docs.pota.app/docs/hunter_guide-english.html).

The useful design ideas are:

- Put the main activity and the next useful action near the top of the page.
- Keep navigation to a small set of task-oriented destinations; move secondary choices into a menu on narrow screens.
- Make search, filters, sorting, and view choice easy to find on data-heavy pages.
- Give live or recently updated items a clear status and timestamp.
- Let people choose a compact table view when scanning many records.

Contestmaster should apply these ideas to contests, log submissions, and published standings. It should not copy POTA's logo, wording, exact page composition, imagery, or product-specific features.

## Approved direction: layout A with a redder palette

On 2026-10-16, the user selected layout A and asked for a more reddish palette in [the approval comment on issue #86](https://github.com/ea7klk/contestmaster/issues/86#issuecomment-6210406692). Use the activity-feed-first landing-page hierarchy, with a deep red-brown header and controls, pale warm surfaces, and a restrained warm accent. Keep body copy and data tables high contrast. Status meaning must not depend on color alone, and final color pairs must be checked against WCAG contrast requirements during implementation.

| Token | Approved value | Use |
| --- | --- | --- |
| Brand 900 | `#511e20` | Header, headings, strong emphasis |
| Brand 700 | `#7d292b` | Primary buttons and selected navigation |
| Brand 600 | `#a33c3d` | Links and secondary actions |
| Accent | `#ce6a54` | Small highlights and focus treatment |
| Canvas | `#f7f0ec` | Application background |
| Surface | `#fffdfa` | Cards, menus, and tables |
| Ink | `#282421` | Main text |
| Muted ink | `#655b55` | Supporting text |
| Border | `#ded2c9` | Separators and control outlines |

Use a compact top bar on desktop with the Contestmaster wordmark, the highest-use destinations, and an account/action area. At a narrow viewport, replace the destination links with a labelled menu button. The menu opens a clearly bounded panel, exposes its expanded state to assistive technology, closes with Escape, and returns focus to the menu button. Navigation remains usable by keyboard and touch. Do not hide the main action (such as “Submit a log”) inside a deep menu.

Retain the shared licensed-data footer on every route. In long data views it can follow the page content; it must remain in the document and reachable by keyboard. Keep form labels, table headings, visible focus, status text, and error explanations. Apply the established accessible form and table practices in [AGENTS.md](../../AGENTS.md) and the [security/accessibility guide](../security/README.md).

Layout A is the approved starting point. The activity-first page should present the public contest activity the API actually provides and must not imply a real-time feed or schedule data that is unavailable. Keep the main log-submission action prominent. Use B and C only as reference for their participant action hierarchy and results-table treatment; they are not alternate implementation targets.

The shared shell uses a compact top bar on desktop and a hamburger menu on narrow screens. The menu opens a clearly bounded panel, exposes its expanded state to assistive technology, closes with Escape and on route selection, and returns focus to its trigger. Navigation remains usable by keyboard and touch. Do not hide the main action (such as “Submit a log”) inside a deep menu.

## Mockup alternatives

Each SVG is a static design study at desktop size. It shows the redder approved palette and an example of the hamburger control; responsive behavior is specified above.

### A — Activity feed first

![Activity feed first mockup](mockups/a-activity-feed.svg)

Opens on current and upcoming contests with quick status filters and direct log submission. This is the closest adaptation of POTA's scan-and-filter rhythm. It makes current activity discoverable, but needs care to avoid suggesting that Contestmaster has a map or real-time spot feed.

### B — Contest dashboard first

![Contest dashboard first mockup](mockups/b-contest-dashboard.svg)

Opens with a clear “find a contest / submit a log” choice, followed by upcoming contests and a separate organizer workspace. This gives new participants a direct route while keeping manager tasks visible to signed-in managers. It has more explanatory content and less at-a-glance density.

### C — Results table first

![Results table first mockup](mockups/c-results-table.svg)

Opens on published standings, with contest selection, category filters, sorting, and a compact results table. This is strongest for returning users who want results quickly, but gives log submission and contest discovery less prominence on the landing page.

## Implementation tracking

Implementation is tracked by [parent issue #87](https://github.com/ea7klk/contestmaster/issues/87): [shared design tokens](https://github.com/ea7klk/contestmaster/issues/88), [responsive navigation](https://github.com/ea7klk/contestmaster/issues/89), [activity-first home page](https://github.com/ea7klk/contestmaster/issues/90), and [responsive contest and participant views](https://github.com/ea7klk/contestmaster/issues/91). Preserve Contestmaster's accessibility and shared licensed-data footer requirements throughout the redesign.
