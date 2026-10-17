import type { RulesetDraft } from '../api/rulesets'
import { translateText } from '../i18n'

type JsonRecord = Record<string, unknown>

export interface SummaryWithBullets {
  introduction: string
  bullets: string[]
  notes?: string[]
}

export type ContestSummaryItem = string | SummaryWithBullets

function tx(source: string, values?: Record<string, string | number>): string {
  return translateText(source, values)
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function stringValue(value: unknown, fallback = ''): string {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter(
        (item): item is string => typeof item === 'string' && !!item.trim(),
      )
    : []
}

function names(values: string[], fallback: string): string {
  if (values.length === 0) return fallback
  if (values.length === 1) return values[0] ?? fallback
  const conjunction = tx('and')
  if (values.length === 2) return `${values[0]} ${conjunction} ${values[1]}`
  return `${values.slice(0, -1).join(', ')}, ${conjunction} ${values.at(-1)}`
}

function formatValueConstraints(field: JsonRecord): string {
  const constraints: string[] = []
  const choices = stringList(field.choices)
  if (choices.length)
    constraints.push(
      tx('allowed values: {values}', { values: names(choices, '') }),
    )
  if (typeof field.pattern === 'string' && field.pattern.trim()) {
    constraints.push(tx('must match {pattern}', { pattern: field.pattern }))
  }
  if (
    typeof field.min_integer === 'number' ||
    typeof field.max_integer === 'number'
  ) {
    const lower =
      typeof field.min_integer === 'number' ? field.min_integer : 'no minimum'
    const upper =
      typeof field.max_integer === 'number' ? field.max_integer : 'no maximum'
    constraints.push(
      tx('integer from {minimum} to {maximum}', {
        minimum: lower,
        maximum: upper,
      }),
    )
  } else if (field.value_type === 'integer' || field.value_type === 'serial') {
    constraints.push(
      field.value_type === 'serial'
        ? tx('positive integer serial number')
        : tx('integer'),
    )
  } else if (typeof field.value_type === 'string') {
    const types: Record<string, string> = {
      callsign: tx('callsign'),
      grid: tx('grid locator'),
      zone: tx('zone identifier'),
      text: tx('text'),
      enum: tx('one of the listed values'),
    }
    if (!choices.length && types[field.value_type])
      constraints.push(types[field.value_type] as string)
  }
  if (typeof field.max_length === 'number') {
    constraints.push(
      tx('up to {count} characters', { count: field.max_length }),
    )
  }
  return constraints.length ? ` (${constraints.join('; ')})` : ''
}

const adifExchangeTags: Record<string, { sent: string; received: string }> = {
  serial: { sent: 'STX or STX_STRING', received: 'SRX or SRX_STRING' },
  grid: { sent: 'MY_GRIDSQUARE', received: 'GRIDSQUARE' },
  report: { sent: 'RST_SENT', received: 'RST_RCVD' },
  state: { sent: 'MY_STATE', received: 'STATE' },
  cq_zone: { sent: 'MY_CQ_ZONE', received: 'CQZ' },
  itu_zone: { sent: 'MY_ITU_ZONE', received: 'ITUZ' },
}

const defaultCabrilloQsoColumns = [
  'frequency',
  'mode',
  'date',
  'time',
  'callsign_sent',
  'rst_sent',
  'exchange_sent',
  'callsign_received',
  'rst_received',
  'exchange_received',
]
const cabrilloQsoColumnAliases: Record<string, string> = {
  band: 'frequency',
  freq: 'frequency',
  time_on: 'time',
  callsign: 'callsign_sent',
  call_sent: 'callsign_sent',
  exch_sent: 'exchange_sent',
  call_rcvd: 'callsign_received',
  callsign_rcvd: 'callsign_received',
  rst_rcvd: 'rst_received',
  exch_rcvd: 'exchange_received',
}

function configuredCabrilloQsoColumns(formatRule: JsonRecord): string[] {
  return stringList(formatRule.qso_columns).map(
    (column) =>
      cabrilloQsoColumnAliases[column.toLowerCase()] ?? column.toLowerCase(),
  )
}

export function hasIncompleteCabrilloQsoColumns(
  ruleset: RulesetDraft | null,
): boolean {
  if (!ruleset || !Array.isArray(ruleset.rules)) return false
  const formatConfig = ruleset.rules.find(
    (configured) =>
      isRecord(configured) &&
      isRecord(configured.rule) &&
      configured.rule.kind === 'format_mapping' &&
      stringValue(configured.rule.format).toLowerCase() === 'cabrillo',
  )
  if (!formatConfig || !isRecord(formatConfig.rule)) return false
  const columns = configuredCabrilloQsoColumns(formatConfig.rule)
  return (
    columns.length > 0 &&
    !defaultCabrilloQsoColumns.every((column) => columns.includes(column))
  )
}

const sampleFrequencyByBand: Record<string, number> = {
  '160m': 1810,
  '80m': 3560,
  '60m': 5357,
  '40m': 7040,
  '30m': 10120,
  '20m': 14025,
  '17m': 18080,
  '15m': 21025,
  '12m': 24900,
  '10m': 28025,
  '6m': 50100,
  '4m': 70100,
  '2m': 144100,
  '1.25m': 222100,
  '70cm': 432100,
  '33cm': 902100,
  '23cm': 1296100,
  '13cm': 2320100,
  '9cm': 3400100,
  '6cm': 5760100,
}
const cabrilloModeByContestMode: Record<string, string> = {
  CW: 'CW',
  PH: 'PH',
  SSB: 'PH',
  AM: 'PH',
  PHONE: 'PH',
  FM: 'FM',
  RY: 'RY',
  RTTY: 'RY',
  DG: 'DG',
  DIGITAL: 'DG',
  PSK31: 'DG',
  PSK63: 'DG',
  FT8: 'DG',
  FT4: 'DG',
  JT65: 'DG',
  JT9: 'DG',
  MSK144: 'DG',
  JS8: 'DG',
  OLIVIA: 'DG',
  MFSK: 'DG',
  SSTV: 'DG',
}

function sampleExchangeValue(
  field: JsonRecord,
  index: number,
  direction: 'sent' | 'received' | 'entry',
): string | null {
  const valueType = stringValue(field.value_type, 'text')
  const maxLength =
    typeof field.max_length === 'number' ? field.max_length : 256
  if (valueType === 'enum') {
    const firstChoice = stringList(field.choices)[0]
    return firstChoice && firstChoice.length <= maxLength ? firstChoice : null
  }

  if (valueType === 'integer' || valueType === 'serial') {
    const minimum =
      typeof field.min_integer === 'number'
        ? field.min_integer
        : valueType === 'serial'
          ? 1
          : 0
    const maximum =
      typeof field.max_integer === 'number'
        ? field.max_integer
        : Number.MAX_SAFE_INTEGER
    const value =
      valueType === 'serial'
        ? minimum + index + (direction === 'received' ? 32 : 0)
        : minimum
    if (value > maximum) return null
    const token = String(value).padStart(Math.min(3, maxLength), '0')
    return token.length <= maxLength ? token : null
  }

  const fieldKey = stringValue(field.key).toLowerCase()
  const candidates =
    valueType === 'callsign'
      ? direction === 'received'
        ? ['K1ABC', 'W1XYZ', 'N0TEST']
        : ['N0TEST', 'K1ABC', 'W1XYZ']
      : valueType === 'grid'
        ? ['FN31', 'EM10', 'FN20']
        : valueType === 'zone'
          ? ['05', '14', '28']
          : fieldKey === 'rst'
            ? ['599']
            : fieldKey === 'section'
              ? ['DX', 'ABC']
              : ['TEST', '599', '1', '001', 'FN31', 'K1ABC', 'DX', 'A']
  const pattern = typeof field.pattern === 'string' ? field.pattern : null
  let expression: RegExp | null = null
  if (pattern) {
    try {
      expression = new RegExp(`^(?:${pattern})$`)
    } catch {
      return null
    }
  }
  return (
    candidates.find(
      (candidate) =>
        candidate.length <= maxLength &&
        (!expression || expression.test(candidate)),
    ) ?? null
  )
}

function sampleCategoryHeader(
  categoryRule: JsonRecord | undefined,
  mappings: unknown,
): string[] | null {
  const dimensions = Array.isArray(categoryRule?.dimensions)
    ? categoryRule.dimensions.filter(isRecord)
    : []
  const requiredKeys = dimensions
    .filter((dimension) => dimension.required !== false)
    .map((dimension) => stringValue(dimension.key))
  const mappingRows = Array.isArray(mappings) ? mappings.filter(isRecord) : []
  const categoryNames: Record<string, string> = {
    assisted: 'ASSISTED',
    band: 'BAND',
    band_class: 'BAND',
    mode: 'MODE',
    operator: 'OPERATOR',
    overlay: 'OVERLAY',
    power: 'POWER',
    station: 'STATION',
    transmitter: 'TRANSMITTER',
    transmitter_count: 'TRANSMITTER',
  }
  if (requiredKeys.length === 0) return []
  if (mappingRows.length === 0) return null

  const selectedHeaders: string[] = []
  const remaining = new Set(requiredKeys)
  while (remaining.size > 0) {
    const selected = mappingRows
      .map((mapping) => {
        const values = isRecord(mapping.category_values)
          ? mapping.category_values
          : {}
        const covered = [...remaining].filter((key) => {
          const choice = values[key]
          const dimension = dimensions.find((item) => item.key === key)
          const choices = Array.isArray(dimension?.choices)
            ? dimension.choices.filter(isRecord).map((item) => item.key)
            : []
          return (
            typeof choice === 'string' &&
            (choices.length === 0 || choices.includes(choice))
          )
        })
        return { mapping, covered }
      })
      .filter((candidate) => candidate.covered.length > 0)
      .sort((left, right) => right.covered.length - left.covered.length)[0]
    if (!selected) return null

    const mappedKeys = isRecord(selected.mapping.category_values)
      ? Object.keys(selected.mapping.category_values)
      : []
    const externalValue = stringValue(selected.mapping.external_value)
    const headerDimension = selected.covered.find(
      (key) => categoryNames[key.toLowerCase()],
    )
    const categoryName = headerDimension
      ? categoryNames[headerDimension.toLowerCase()]
      : undefined
    if (!externalValue || !categoryName || mappedKeys.length === 0) return null
    selectedHeaders.push(`CATEGORY-${categoryName}: ${externalValue}`)
    selected.covered.forEach((key) => remaining.delete(key))
  }
  return selectedHeaders
}

/** Build a minimal Cabrillo 3.0 example from ruleset constraints, or omit it when unsafe. */
export function generateCabrilloExample(
  ruleset: RulesetDraft | null,
  contest?: {
    name: string
    slug: string
    starts_at: string
    ends_at: string
  },
): string | null {
  if (!ruleset || !contest || !Array.isArray(ruleset.rules)) return null
  const configuredRules = ruleset.rules.filter(
    (configured) => isRecord(configured) && isRecord(configured.rule),
  )
  const formatConfig = configuredRules.find(
    (configured) =>
      configured.rule.kind === 'format_mapping' &&
      stringValue(configured.rule.format).toLowerCase() === 'cabrillo',
  )
  if (!formatConfig || isRecord(formatConfig.when)) return null

  const rules = configuredRules.map((configured) => configured.rule)
  const eligibility = rules.find((rule) => rule.kind === 'eligibility')
  if (
    configuredRules.some(
      (configured) =>
        (configured.rule.kind === 'eligibility' ||
          configured.rule.kind === 'exchange' ||
          configured.rule.kind === 'categories') &&
        isRecord(configured.when),
    )
  )
    return null

  const allowedBands = eligibility ? stringList(eligibility.allowed_bands) : []
  const band = allowedBands.length
    ? allowedBands.find((value) => sampleFrequencyByBand[value.toLowerCase()])
    : '20m'
  if (!band) return null
  const frequency = sampleFrequencyByBand[band.toLowerCase()]
  if (!frequency) return null
  const allowedModes = eligibility ? stringList(eligibility.allowed_modes) : []
  const mode = allowedModes.length
    ? allowedModes
        .map((candidate) => cabrilloModeByContestMode[candidate.toUpperCase()])
        .find((candidate) => candidate !== undefined)
    : 'CW'
  if (!mode) return null
  const exchangeRule = rules.find((rule) => rule.kind === 'exchange')
  const exchangeFields = Array.isArray(exchangeRule?.fields)
    ? exchangeRule.fields.filter(isRecord)
    : []
  const categoryRule = rules.find((rule) => rule.kind === 'categories')
  const categoryHeader = sampleCategoryHeader(
    categoryRule,
    formatConfig.rule.category_mappings,
  )
  if (categoryHeader === null) return null

  const start = Date.parse(contest.starts_at)
  const end = Date.parse(contest.ends_at)
  if (!Number.isFinite(start) || !Number.isFinite(end)) return null
  const qsoInstant = Math.ceil(start / 60_000) * 60_000
  if (qsoInstant >= end) return null

  const headerFields = isRecord(formatConfig.rule.header_fields)
    ? formatConfig.rule.header_fields
    : {}
  const headerName = (key: string, fallback: string) =>
    stringValue(headerFields[key], fallback).toUpperCase()
  const headerLines = [
    'START-OF-LOG: 3.0',
    `${headerName('contest', 'CONTEST')}: ${contest.slug || contest.name}`,
    `${headerName('callsign', 'CALLSIGN')}: N0TEST`,
  ]

  for (const field of exchangeFields.filter(
    (item) => item.direction === 'entry',
  )) {
    const header = headerName(stringValue(field.key), stringValue(field.key))
    const value = sampleExchangeValue(field, 0, 'entry')
    if (!value) return null
    headerLines.push(`${header}: ${value}`)
  }

  const configuredColumns = configuredCabrilloQsoColumns(formatConfig.rule)
  const columns = configuredColumns.length
    ? configuredColumns
    : defaultCabrilloQsoColumns
  if (!defaultCabrilloQsoColumns.every((column) => columns.includes(column)))
    return null
  const extraColumns = columns.filter(
    (column) => !defaultCabrilloQsoColumns.includes(column),
  )
  if (
    !defaultCabrilloQsoColumns.every((column) => columns.includes(column)) ||
    extraColumns.some((column) => column !== 'transmitter')
  )
    return null

  const makeExchange = (direction: 'sent' | 'received', index: number) => {
    const fields = exchangeFields.filter(
      (field) => field.direction === direction || field.direction === 'both',
    )
    if (fields.length === 0) return 'TEST'
    const tokens = fields.map((field) =>
      sampleExchangeValue(field, index, direction),
    )
    return tokens.every((value): value is string => value !== null)
      ? tokens.join(' ')
      : null
  }

  const qsos = [0, 1].map((index) => {
    const exchangeSent = makeExchange('sent', index)
    const exchangeReceived = makeExchange('received', index)
    if (exchangeSent === null || exchangeReceived === null) return null
    const instant = new Date(qsoInstant).toISOString()
    const date = instant.slice(0, 10)
    const time = instant.slice(11, 16).replace(':', '')
    const fields: Record<string, string> = {
      frequency: String(frequency),
      mode,
      date,
      time,
      callsign_sent: 'N0TEST',
      rst_sent: '599',
      exchange_sent: exchangeSent,
      callsign_received: index === 0 ? 'K1ABC' : 'W1XYZ',
      rst_received: '599',
      exchange_received: exchangeReceived,
    }
    for (const column of columns) {
      if (!(column in fields))
        fields[column] = column === 'transmitter' ? '1' : 'TEST'
    }
    return columns.map((column) => fields[column] ?? '').join(' ')
  })
  if (qsos.some((line) => line === null)) return null
  const validQsos = qsos.filter((line): line is string => line !== null)
  return [
    ...headerLines,
    ...categoryHeader,
    ...validQsos.map((qso) => `QSO: ${qso}`),
    'END-OF-LOG:',
  ].join('\n')
}

function requiredExchangeEntries(
  rule: JsonRecord | undefined,
  format: string,
): string[] {
  if (!rule || !Array.isArray(rule.fields)) return []
  const requiredFields = rule.fields.filter(
    (field): field is JsonRecord => isRecord(field) && field.required !== false,
  )
  return requiredFields.map((field) => {
    const label = stringValue(
      field.label,
      stringValue(field.key, tx('exchange value')),
    )
    const direction = stringValue(field.direction, 'both')
    const directionText =
      {
        sent: tx('sent'),
        received: tx('received'),
        both: tx('sent and received'),
        entry: tx('declared for the entry'),
      }[direction] ?? direction
    const tags = adifExchangeTags[stringValue(field.key)]
    const tagText =
      format === 'adif' && tags && direction !== 'entry'
        ? ` [ADIF: ${direction === 'sent' ? tags.sent : direction === 'received' ? tags.received : `${tags.sent} / ${tags.received}`}]`
        : ''
    return tx('{label} ({direction}){tagText}{constraints}', {
      label,
      direction: directionText,
      tagText,
      constraints: formatValueConstraints(field),
    })
  })
}

function describeRequiredExchangeFields(
  rule: JsonRecord | undefined,
  format: string,
  condition?: string,
): string {
  const entries = requiredExchangeEntries(rule, format)
  if (!entries.length) return ''
  return condition
    ? tx(
        ' Required contest exchange fields and constraints when {condition}: {entries}.',
        {
          condition,
          entries: entries.join('; '),
        },
      )
    : tx(' Required contest exchange fields and constraints: {entries}.', {
        entries: entries.join('; '),
      })
}

function describeLogSubmissionRequirements(
  ruleset: RulesetDraft,
  contest?: { name: string; slug: string },
): ContestSummaryItem[] {
  const configuredRules = ruleset.rules.filter((configured) =>
    isRecord(configured.rule),
  )
  const rules = configuredRules.map((configured) => configured.rule)
  const formats = rules.filter((rule) => rule.kind === 'format_mapping')
  if (!formats.length) return []

  const eligibilityConfig = configuredRules.find(
    (configured) => configured.rule.kind === 'eligibility',
  )
  const eligibility = eligibilityConfig?.rule
  const eligibilityCondition = isRecord(eligibilityConfig?.when)
    ? tx(' when {condition}', {
        condition: describeCondition(eligibilityConfig.when),
      })
    : ''
  const allowedBands = eligibility ? stringList(eligibility.allowed_bands) : []
  const allowedModes = eligibility ? stringList(eligibility.allowed_modes) : []
  const bandConstraint = (format: string) =>
    allowedBands.length
      ? tx(
          'Allowed band values{condition}: {bands}; frequency values must fall within these bands.',
          {
            condition: eligibilityCondition,
            bands: names(allowedBands, ''),
          },
        )
      : tx(
          'No band restriction is configured; provide {field} accepted by the importer.',
          {
            field:
              format === 'cabrillo'
                ? tx('a Cabrillo frequency or band token')
                : tx('an ADIF BAND or supported FREQ'),
          },
        )
  const modeConstraint = (format: string) =>
    allowedModes.length
      ? tx('Allowed mode values{condition}: {modes}.', {
          condition: eligibilityCondition,
          modes: names(allowedModes, ''),
        })
      : format === 'cabrillo'
        ? tx(
            'No contest mode restriction is configured; standard Cabrillo mode tokens include CW, PH, FM, RY, and DG.',
          )
        : tx(
            'No contest mode restriction is configured; use the ADIF MODE or SUBMODE required by the sponsor.',
          )
  const exchangeConfig = configuredRules.find(
    (configured) => configured.rule.kind === 'exchange',
  )
  const exchange = exchangeConfig?.rule
  const exchangeCondition = isRecord(exchangeConfig?.when)
    ? describeCondition(exchangeConfig.when)
    : undefined

  return [
    ...new Set(
      formats.map((format) => stringValue(format.format).toLowerCase()),
    ),
  ]
    .filter((format) => format === 'cabrillo' || format === 'adif')
    .map((format) => {
      const exchangeDetails = describeRequiredExchangeFields(
        exchange,
        format,
        exchangeCondition,
      )
      if (format === 'cabrillo') {
        const contestHeader = contest
          ? tx('CONTEST must match “{name}” or “{slug}”', {
              name: contest.name,
              slug: contest.slug,
            })
          : tx('CONTEST must match the selected contest')
        return {
          introduction: tx('Required Cabrillo fields:'),
          bullets: [
            tx(
              'START-OF-LOG: 2.0 or 3.0. The importer also accepts legacy unversioned markers.',
            ),
            tx('END-OF-LOG: terminates the log records.'),
            tx(
              'CALLSIGN: non-empty header value. CONTEST: non-empty header value; {contestHeader}.',
              { contestHeader },
            ),
            `${tx('Each QSO must include frequency or band.')} (FREQ or BAND)`,
            `${tx('Each QSO must include mode.')} (MODE)`,
            `${tx('Each QSO must include date in UTC as YYYY-MM-DD.')} (DATE)`,
            tx(
              'Each QSO must include time in UTC as HHMM (HHMMSS is also accepted).',
            ) + ' (TIME)',
            tx(
              'Each QSO must include sent callsign, sent RST, and sent exchange.',
            ) + ' (CALLSIGN, RST, EXCHANGE sent)',
            tx(
              'Each QSO must include received callsign, received RST, and received exchange.',
            ) + ' (CALLSIGN, RST, EXCHANGE received)',
            tx(
              'Callsigns may contain A–Z, 0–9, and /. RST reports and exchange tokens must be non-empty.',
            ),
            bandConstraint(format),
            modeConstraint(format),
            ...requiredExchangeEntries(exchange, format).map((entry) =>
              exchangeCondition
                ? tx('Required exchange: {entry} when {condition}.', {
                    entry,
                    condition: exchangeCondition,
                  })
                : tx('Required exchange: {entry}.', { entry }),
            ),
          ],
        }
      }
      return tx(
        'Required ADIF fields: identify the station with STATION_CALLSIGN or OPERATOR in the header or a QSO record; every QSO record must end with <EOR> and include QSO_DATE (valid UTC date as YYYYMMDD), TIME_ON (HHMM or HHMMSS UTC), CALL (callsign), MODE or SUBMODE, BAND or FREQ in MHz, and sent and received exchange data. {bandConstraint} {modeConstraint}{exchangeDetails}',
        {
          bandConstraint: bandConstraint(format),
          modeConstraint: modeConstraint(format),
          exchangeDetails,
        },
      )
    })
}

const categoryMeanings: Record<string, string> = {
  operator: tx(
    'classifies the operator arrangement; the contest rules define operator eligibility, operating-time, and transmitter limits',
  ),
  power: tx('classifies station transmit output power'),
  band: tx(
    'classifies all-band or single-band entry types; the contest rules define eligible bands and how band combinations are scored',
  ),
  mode: tx(
    'classifies operating modes; the contest rules define included modes and mixed-mode requirements',
  ),
  assisted: tx(
    'indicates whether operating assistance is used; the contest rules define which tools count as assistance',
  ),
  transmitter: tx(
    'classifies transmitter configuration; the contest rules define simultaneous transmitter and band-change limits',
  ),
  overlay: tx(
    'is an additional sponsor-defined classification that may apply alongside a main category',
  ),
  station_class: tx(
    'classifies station type or capability; the contest rules define location, portability, and equipment requirements',
  ),
  region: tx(
    'groups entries by geography; the contest rules define the region boundaries and assignment source',
  ),
  category: tx('is a sponsor-defined grouping of entries'),
}

const powerChoiceMeanings: Record<string, string> = {
  qrp: tx('Maximum transmit output: 5 W.'),
  low: tx('Maximum transmit output: 100 W.'),
  high: tx('Maximum transmit output: up to the applicable legal limit.'),
}

function categoryDimensionKind(key: string, label: string): string {
  const source = `${key} ${label}`.toLowerCase().replaceAll('_', ' ')
  for (const [term, kind] of [
    ['operator', 'operator'],
    ['power', 'power'],
    ['band', 'band'],
    ['mode', 'mode'],
    ['assist', 'assisted'],
    ['transmitter', 'transmitter'],
    ['overlay', 'overlay'],
    ['station class', 'station_class'],
    ['region', 'region'],
    ['category', 'category'],
  ]) {
    if (source.includes(term)) return kind
  }
  return key
}

function categoryChoiceMeaning(
  dimensionKey: string,
  choice: JsonRecord,
): string {
  const customDescription = stringValue(choice.description)
  if (customDescription) return customDescription
  return dimensionKey === 'power'
    ? (powerChoiceMeanings[stringValue(choice.key)] ?? '')
    : ''
}

function describeCondition(value: unknown): string {
  if (!isRecord(value)) return tx('the configured condition')
  if (value.kind === 'compare') {
    const fact = stringValue(value.fact, tx('configured contest value'))
      .replace(/^qso\./, `${tx('contact')} `)
      .replace(/^entry\./, `${tx('entry')} `)
      .replace(/^station\./, `${tx('station')} `)
      .replace(/^exchange\./, `${tx('exchange')} `)
      .replaceAll('_', ' ')
    const operator = {
      eq: tx('is'),
      ne: tx('is not'),
      in: tx('is one of'),
      not_in: tx('is not one of'),
      lt: tx('is less than'),
      lte: tx('is at most'),
      gt: tx('is greater than'),
      gte: tx('is at least'),
      matches: tx('matches'),
      exists: tx('is present'),
    }[stringValue(value.operator)]
    if (value.operator === 'exists') return `${fact} ${operator}`
    const expected = Array.isArray(value.value)
      ? names(value.value.map(String), tx('the configured values'))
      : String(value.value ?? tx('the configured value'))
    return `${fact} ${operator ?? tx('matches')} ${expected}`
  }
  if (value.kind === 'all' || value.kind === 'any') {
    const conditions = Array.isArray(value.conditions)
      ? value.conditions.map(describeCondition)
      : []
    return conditions.length
      ? conditions.join(
          value.kind === 'all' ? ` ${tx('and')} ` : ` ${tx('or')} `,
        )
      : tx('the configured conditions')
  }
  if (value.kind === 'not') {
    return tx('not ({condition})', {
      condition: describeCondition(value.condition),
    })
  }
  return tx('the configured condition')
}

function summarizeRule(rule: JsonRecord): ContestSummaryItem {
  switch (rule.kind) {
    case 'submission': {
      const latePolicy = {
        reject: tx('Late logs are rejected.'),
        accept_late: tx('Late logs may be accepted and marked late.'),
        checklog: tx('Late logs are classified for checklog review.'),
      }[stringValue(rule.late_policy)]
      return `${latePolicy ?? tx('The late-log policy is defined by the contest.')}${
        rule.manager_extension_allowed === true
          ? tx(' A contest manager may extend the submission cutoff.')
          : ''
      }`
    }
    case 'categories': {
      const dimensionRows = Array.isArray(rule.dimensions)
        ? rule.dimensions.filter(isRecord)
        : []
      const dimensions = dimensionRows.map((dimension) => {
        const choiceRows = Array.isArray(dimension.choices)
          ? dimension.choices.filter(isRecord)
          : []
        const choices = choiceRows.map((choice) =>
          stringValue(choice.label, stringValue(choice.key)),
        )
        const key = stringValue(dimension.key)
        const label = stringValue(
          dimension.label,
          stringValue(dimension.key, tx('Category')),
        )
        const dimensionKind = categoryDimensionKind(key, label)
        const requirement =
          dimension.required === false ? tx('optional') : tx('required')
        const meaning =
          stringValue(dimension.description) ||
          categoryMeanings[dimensionKind] ||
          tx(
            'is a sponsor-defined classification; check the official rules for its exact definition and limits',
          )
        const choiceDefinitions = choiceRows
          .map((choice) => {
            const meaning = categoryChoiceMeaning(dimensionKind, choice)
            return meaning
              ? tx('{label}: {meaning}', {
                  label: stringValue(choice.label, stringValue(choice.key)),
                  meaning,
                })
              : ''
          })
          .filter(Boolean)
        const values = choices.length
          ? tx(': {choices}', { choices: names(choices, '') })
          : ''
        const choiceText = choiceDefinitions.length
          ? tx(' Choice details: {details}.', {
              details: choiceDefinitions.join('; '),
            })
          : ''
        return tx(
          '{label} ({requirement}){values}. This {meaning}.{choiceText}',
          { label, requirement, values, meaning, choiceText },
        )
      })
      const exclusions = Array.isArray(rule.mutually_exclusive)
        ? rule.mutually_exclusive
            .filter(Array.isArray)
            .map((group) =>
              group.map((key) => {
                const dimension = dimensionRows.find(
                  (candidate) => candidate.key === key,
                )
                return isRecord(dimension)
                  ? stringValue(dimension.label, String(key))
                  : String(key)
              }),
            )
            .filter((group) => group.length > 1)
        : []
      if (dimensions.length === 0) {
        return tx('Entry categories are configured for this contest.')
      }
      const summary = tx(
        'Categories divide entries into separate classification dimensions. Participants select one value for each required dimension; optional dimensions may be left blank.',
      )
      const declarationChoices = dimensionRows.flatMap((dimension) => {
        const dimensionLabel = stringValue(
          dimension.label,
          stringValue(dimension.key, tx('Category')),
        )
        return Array.isArray(dimension.choices)
          ? dimension.choices
              .filter(isRecord)
              .filter((choice) => choice.requires_declaration === true)
              .map((choice) =>
                tx('{choice} in {dimension}', {
                  choice: stringValue(
                    choice.label,
                    stringValue(choice.key, tx('Category choice')),
                  ),
                  dimension: dimensionLabel,
                }),
              )
          : []
      })
      const hasGeneratedPowerLimits = dimensionRows.some((dimension) => {
        const key = stringValue(dimension.key)
        const label = stringValue(dimension.label, key)
        if (categoryDimensionKind(key, label) !== 'power') return false
        return Array.isArray(dimension.choices)
          ? dimension.choices.some(
              (choice) =>
                isRecord(choice) &&
                !stringValue(choice.description) &&
                Object.hasOwn(powerChoiceMeanings, stringValue(choice.key)),
            )
          : false
      })
      const notes = [
        tx(
          'Exact qualifications and limits are contest-specific; the official published rules are authoritative.',
        ),
        ...(declarationChoices.length
          ? [
              tx('The ruleset marks {choices} as requiring a declaration.', {
                choices: names(declarationChoices, tx('the marked choices')),
              }),
            ]
          : []),
        ...(exclusions.length
          ? [
              tx('These dimensions cannot be combined: {groups}.', {
                groups: exclusions
                  .map((group) => names(group, tx('configured dimensions')))
                  .join('; '),
              }),
            ]
          : []),
        ...(hasGeneratedPowerLimits
          ? [
              tx(
                'Unless contest rules specify otherwise, these are the assumed power limits; the official rules define where power is measured.',
              ),
            ]
          : []),
      ]
      return { introduction: summary, bullets: dimensions, notes }
    }
    case 'exchange': {
      const fields = Array.isArray(rule.fields)
        ? rule.fields.filter(isRecord).map((field) => {
            const label = stringValue(
              field.label,
              stringValue(field.key, tx('exchange value')),
            )
            const direction = stringValue(field.direction)
            const directionText = {
              sent: tx('sent'),
              received: tx('received'),
              both: tx('sent and received'),
              entry: tx('declared for the entry'),
            }[direction]
            return directionText
              ? tx('{label} ({direction})', { label, direction: directionText })
              : label
          })
        : []
      return fields.length
        ? tx('Stations exchange {fields}.', {
            fields: names(fields, tx('the configured exchange fields')),
          })
        : tx('Stations use the exchange fields configured for this contest.')
    }
    case 'eligibility': {
      const bands = stringList(rule.allowed_bands)
      const modes = stringList(rule.allowed_modes)
      const limits = [
        bands.length
          ? tx('bands {bands}', { bands: names(bands, '') })
          : tx('all bands'),
        modes.length
          ? tx('modes {modes}', { modes: names(modes, '') })
          : tx('all modes'),
      ]
      const checks = [
        rule.reject_self_contacts === true
          ? tx('self-contacts are excluded')
          : '',
        rule.reject_out_of_period === true
          ? tx('contacts outside the contest period are excluded')
          : '',
        rule.reject_missing_required_exchange === true
          ? tx('contacts missing required exchange details are excluded')
          : '',
        rule.eligible_if !== undefined && rule.eligible_if !== null
          ? tx('additional configured contact conditions apply')
          : '',
      ].filter(Boolean)
      return tx('Eligible contacts may use {limits}.{checks}', {
        limits: names(limits, tx('the configured operating limits')),
        checks: checks.length ? ` ${names(checks, '')}.` : '',
      })
    }
    case 'duplicates': {
      const scope = stringList(rule.scope).map(
        (item) =>
          ({
            worked_callsign: tx('the same callsign'),
            band: tx('the same band'),
            mode: tx('the same mode'),
            grid: tx('the same grid square'),
            transmitter: tx('the same transmitter'),
          })[item] ?? item,
      )
      const effect = {
        ignore: tx('ignored'),
        not_credited: tx('not credited'),
        penalty: tx('subject to a penalty'),
        needs_review: tx('sent for review'),
      }[stringValue(rule.effect)]
      return tx('A contact repeated with {scope} is {effect}.', {
        scope: names(scope, tx('the configured duplicate identity')),
        effect: effect ?? tx('handled by the configured duplicate policy'),
      })
    }
    case 'points': {
      const fact = stringValue(rule.fact)
      if (fact === 'fixed' && typeof rule.fixed_points === 'number') {
        return tx('Each eligible contact is worth {points} points.', {
          points: rule.fixed_points,
        })
      }
      const values = isRecord(rule.values) ? Object.entries(rule.values) : []
      const examples = values
        .slice(0, 4)
        .map(([key, value]) =>
          tx('{key}: {points} points', { key, points: String(value) }),
        )
      const remainder =
        values.length > examples.length
          ? tx(', plus {count} other values', {
              count: values.length - examples.length,
            })
          : ''
      const defaultPoints =
        typeof rule.default_points === 'number'
          ? tx(
              ' Contacts without a matching value are worth {points} points.',
              { points: rule.default_points },
            )
          : ''
      return examples.length
        ? tx(
            'Contact points are based on {fact} ({examples}{remainder}).{defaultPoints}',
            {
              fact: fact || tx('configured contact details'),
              examples: examples.join('; '),
              remainder,
              defaultPoints,
            },
          )
        : tx('Contact points are based on {fact}.', {
            fact: fact || tx('the configured scoring rule'),
          })
    }
    case 'multiplier': {
      const source = stringValue(
        rule.source_fact,
        tx('the configured exchange or contact value'),
      )
      const scope = stringValue(rule.scope, tx('contest'))
      return tx('Multipliers come from {source} and count once per {scope}.', {
        source,
        scope: scope.replaceAll('_', ' '),
      })
    }
    case 'bonus': {
      const points =
        typeof rule.points === 'number' ? String(rule.points) : tx('configured')
      const basis =
        rule.basis === 'per_entry'
          ? tx('per entry')
          : tx('per eligible contact')
      const cap =
        typeof rule.cap === 'number'
          ? tx(', up to {points} points', { points: rule.cap })
          : ''
      const minimum =
        typeof rule.minimum_eligible_qsos === 'number' &&
        rule.minimum_eligible_qsos > 0
          ? tx(' after at least {count} eligible contacts', {
              count: rule.minimum_eligible_qsos,
            })
          : ''
      const evidence =
        typeof rule.evidence_key === 'string'
          ? tx(' Evidence declaration “{key}” is required.', {
              key: rule.evidence_key,
            })
          : ''
      return tx('Bonus: {points} points {basis}{cap}{minimum}.{evidence}', {
        points,
        basis,
        cap,
        minimum,
        evidence,
      })
    }
    case 'penalty': {
      const action = stringValue(
        rule.action,
        tx('the configured consequence'),
      ).replaceAll('_', ' ')
      const points =
        typeof rule.points === 'number' && rule.points > 0
          ? tx(' ({points} points)', { points: rule.points })
          : ''
      const maximum =
        typeof rule.maximum_occurrences === 'number' &&
        rule.maximum_occurrences > 1
          ? tx(', up to {count} times', { count: rule.maximum_occurrences })
          : ''
      return tx('For {reason}, the penalty is to {action}{points}{maximum}.', {
        reason: stringValue(rule.reason_code, tx('a configured violation')),
        action,
        points,
        maximum,
      })
    }
    case 'score_formula': {
      const variableNames: Record<string, string> = {
        points_total: tx('contact points'),
        multiplier_count: tx('multipliers'),
        bonus_points: tx('bonus points'),
        penalty_points: tx('penalty points'),
        power_multiplier: tx('power multiplier'),
      }
      const operand = (value: unknown) => {
        if (!isRecord(value)) return tx('a configured value')
        if (typeof value.constant === 'number') return String(value.constant)
        return (
          variableNames[stringValue(value.variable)] ?? tx('a configured value')
        )
      }
      const operators: Record<string, string> = {
        add: tx('plus'),
        subtract: tx('minus'),
        multiply: tx('multiplied by'),
        floor_divide: tx('divided by'),
        round_divide: tx('divided by'),
      }
      const steps = Array.isArray(rule.steps) ? rule.steps.filter(isRecord) : []
      const expression = [
        operand(rule.start),
        ...steps.map((step) => {
          const rounding =
            step.operator === 'round_divide' &&
            typeof step.rounding === 'string'
              ? tx(' ({rounding} rounding)', {
                  rounding: step.rounding.replaceAll('_', ' '),
                })
              : ''
          return tx('{operator} {operand}{rounding}', {
            operator:
              operators[stringValue(step.operator)] ?? tx('combined with'),
            operand: operand(step.operand),
            rounding,
          })
        }),
      ]
      return tx('Final score: {expression}. Scores use whole-number points.', {
        expression: expression.join(' '),
      })
    }
    case 'operating_constraints': {
      const limits = [
        typeof rule.max_operating_minutes === 'number' &&
          tx('up to {count} operating minutes', {
            count: rule.max_operating_minutes,
          }),
        typeof rule.maximum_band_changes === 'number' &&
          tx('up to {count} band changes', {
            count: rule.maximum_band_changes,
          }),
        typeof rule.maximum_transmitters === 'number' &&
          tx('up to {count} transmitters', {
            count: rule.maximum_transmitters,
          }),
        typeof rule.minimum_off_time_minutes === 'number' &&
          rule.minimum_off_time_minutes > 0 &&
          tx('{count} minutes of off time', {
            count: rule.minimum_off_time_minutes,
          }),
        typeof rule.required_off_periods === 'number' &&
          rule.required_off_periods > 0 &&
          tx('{count} required off periods', {
            count: rule.required_off_periods,
          }),
        typeof rule.minimum_band_dwell_minutes === 'number' &&
          tx('{count}-minute minimum band dwell', {
            count: rule.minimum_band_dwell_minutes,
          }),
        rule.one_transmitted_signal_per_band === true &&
          tx('one transmitted signal per band'),
      ].filter((item): item is string => typeof item === 'string')
      return limits.length
        ? tx('Operating limits include {limits}.', {
            limits: names(limits, tx('the configured station rules')),
          })
        : tx('Operating and station limits follow the contest configuration.')
    }
    case 'format_mapping':
      return tx('{format} log format is accepted.{preserved}', {
        format: stringValue(rule.format, tx('The configured')),
        preserved:
          rule.preserve_unknown_fields === true
            ? tx(' Unrecognized fields are retained for review.')
            : '',
      })
    case 'workflow_hook': {
      const stage = stringValue(rule.stage, 'contest')
      const execution = {
        automatic: tx('runs automatically'),
        declaration: tx('uses participant declarations'),
        human_review: tx('requires human review'),
      }[stringValue(rule.execution)]
      return tx('{stage} processing {execution}.', {
        stage: stage.charAt(0).toUpperCase() + stage.slice(1),
        execution: execution ?? tx('follows the configured workflow'),
      })
    }
    default:
      return tx('Additional contest rule configured: {kind}.', {
        kind: stringValue(rule.kind, tx('unspecified')),
      })
  }
}

export function describeContestRuleset(
  ruleset: RulesetDraft | null,
  contest?: { name: string; slug: string },
): ContestSummaryItem[] {
  if (!ruleset || !Array.isArray(ruleset.rules)) return []
  const descriptions = ruleset.rules.flatMap((configured) => {
    if (!isRecord(configured) || !isRecord(configured.rule)) return []
    const summary = summarizeRule(configured.rule)
    if (configured.when === undefined || configured.when === null)
      return [summary]
    const conditionPrefix = tx('Only when {condition}: ', {
      condition: describeCondition(configured.when),
    })
    if (typeof summary === 'string') {
      return [
        `${conditionPrefix}${summary.charAt(0).toLowerCase()}${summary.slice(1)}`,
      ]
    }
    return [
      {
        ...summary,
        introduction: `${conditionPrefix}${summary.introduction.charAt(0).toLowerCase()}${summary.introduction.slice(1)}`,
      },
    ]
  })
  return [
    ...descriptions,
    ...describeLogSubmissionRequirements(ruleset, contest),
  ]
}
