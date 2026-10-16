# Interface languages

The frontend interface is available in English, German, French, Spanish, and Italian. English is the source catalog and runtime fallback. The non-English catalogs are loaded only when selected.

On a first visit, the application chooses the first supported language in the browser's language preference list and uses English if none match. A language selected in the navigation takes precedence on later visits and is stored in browser local storage. Selection does not require an account or change server data. The selector uses native language names and updates the document language for assistive technology.

## Editing interface messages

Keep app-authored interface text in the Vue I18n catalogs under `frontend/src/i18n/locales/`. In a Vue template, use `$tr('English source text')`; in TypeScript, use `translateText('English source text')`. The source text determines a stable message key, so keep the English wording consistent across call sites. Add the same message key to all four translated catalogs. Preserve interpolation names such as `{count}` exactly in every language.

Do not translate callsigns, uploaded log contents, ruleset keys, master-data values, sponsor names, or contest-manager-authored descriptions. These are application data, not interface messages. Built-in category and exchange presets may show localized labels while keeping their configured values stable.

Date and number displays should use the shared helpers in `frontend/src/i18n/index.ts`. Contest instants are formatted in UTC and retain an explicit `UTC` suffix. Scores and scoring counts use integer formatting and reject fractional values.

## Verification

Run the catalog completeness check and frontend checks before merging localization changes:

```sh
cd frontend
npm run i18n:check
npm test -- --run src/i18n/index.test.ts src/App.test.ts
npm run lint
npm run typecheck
npm run build
```

The completeness check verifies catalog key parity, non-empty messages, matching interpolation placeholders, and coverage of literal `$tr()` and `translateText()` calls. Review wording in context, especially amateur-radio terms such as exchange, serial, multiplier, and log, before release.
