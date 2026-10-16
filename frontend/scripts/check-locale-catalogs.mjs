import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import console from 'node:console'
import { fileURLToPath } from 'node:url'

const frontendRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
)
const sourceRoot = path.join(frontendRoot, 'src')
const localeRoot = path.join(sourceRoot, 'i18n', 'locales')
const locales = ['en', 'de', 'fr', 'es', 'it']
const catalogs = Object.fromEntries(
  locales.map((locale) => [
    locale,
    JSON.parse(
      fs.readFileSync(path.join(localeRoot, `${locale}.json`), 'utf8'),
    ),
  ]),
)

function messageKey(sourceText) {
  let hash = 0x811c9dc5
  for (let index = 0; index < sourceText.length; index += 1) {
    hash ^= sourceText.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193)
  }
  return `s_${(hash >>> 0).toString(16).padStart(8, '0')}`
}

function sourceFiles(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const target = path.join(directory, entry.name)
    if (entry.isDirectory()) return sourceFiles(target)
    if (!/\.(vue|ts)$/.test(entry.name) || /\.test\.ts$/.test(entry.name))
      return []
    if (target.includes(`${path.sep}i18n${path.sep}locales${path.sep}`))
      return []
    return [target]
  })
}

const englishKeys = Object.keys(catalogs.en).sort()
const failures = []
for (const locale of locales.slice(1)) {
  const actual = Object.keys(catalogs[locale]).sort()
  if (JSON.stringify(actual) !== JSON.stringify(englishKeys)) {
    failures.push(`${locale} catalog keys do not match English`)
  }
  for (const key of englishKeys) {
    if (!catalogs[locale][key])
      failures.push(`${locale} has an empty value for ${key}`)
    const placeholders = (value) =>
      [...String(value).matchAll(/\{[^{}]+\}/g)].map((match) => match[0]).sort()
    if (
      JSON.stringify(placeholders(catalogs.en[key])) !==
      JSON.stringify(placeholders(catalogs[locale][key]))
    ) {
      failures.push(`${locale} has mismatched placeholders for ${key}`)
    }
  }
}

const callPattern =
  /(?:\$tr|translateText)\(\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g
for (const file of sourceFiles(sourceRoot)) {
  const source = fs.readFileSync(file, 'utf8')
  for (const match of source.matchAll(callPattern)) {
    let message
    try {
      message = match[1].startsWith('"')
        ? JSON.parse(match[1])
        : match[1].slice(1, -1).replaceAll("\\'", "'")
    } catch {
      failures.push(
        `${path.relative(frontendRoot, file)} has an invalid translation literal`,
      )
      continue
    }
    const key = messageKey(message)
    if (!(key in catalogs.en)) {
      failures.push(
        `${path.relative(frontendRoot, file)} is missing catalog message: ${message}`,
      )
    }
  }
}

if (failures.length) {
  console.error(failures.join('\n'))
  process.exitCode = 1
} else {
  console.log(
    `Locale catalogs are complete: ${locales.join(', ')} (${englishKeys.length} messages).`,
  )
}
