import type { RulesetDraft } from '../api/rulesets'

type JsonRecord = Record<string, unknown>

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
  if (values.length === 2) return `${values[0]} and ${values[1]}`
  return `${values.slice(0, -1).join(', ')}, and ${values.at(-1)}`
}

function formatValueConstraints(field: JsonRecord): string {
  const constraints: string[] = []
  const choices = stringList(field.choices)
  if (choices.length) constraints.push(`allowed values: ${names(choices, '')}`)
  if (typeof field.pattern === 'string' && field.pattern.trim()) {
    constraints.push(`must match ${field.pattern}`)
  }
  if (
    typeof field.min_integer === 'number' ||
    typeof field.max_integer === 'number'
  ) {
    const lower =
      typeof field.min_integer === 'number' ? field.min_integer : 'no minimum'
    const upper =
      typeof field.max_integer === 'number' ? field.max_integer : 'no maximum'
    constraints.push(`integer from ${lower} to ${upper}`)
  } else if (field.value_type === 'integer' || field.value_type === 'serial') {
    constraints.push(
      field.value_type === 'serial'
        ? 'positive integer serial number'
        : 'integer',
    )
  } else if (typeof field.value_type === 'string') {
    const types: Record<string, string> = {
      callsign: 'callsign',
      grid: 'grid locator',
      zone: 'zone identifier',
      text: 'text',
      enum: 'one of the listed values',
    }
    if (!choices.length && types[field.value_type])
      constraints.push(types[field.value_type] as string)
  }
  if (typeof field.max_length === 'number') {
    constraints.push(`up to ${field.max_length} characters`)
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

function describeRequiredExchangeFields(
  rule: JsonRecord | undefined,
  format: string,
  condition?: string,
): string {
  if (!rule || !Array.isArray(rule.fields)) return ''
  const requiredFields = rule.fields.filter(
    (field): field is JsonRecord => isRecord(field) && field.required !== false,
  )
  if (!requiredFields.length) return ''
  const entries = requiredFields.map((field) => {
    const label = stringValue(
      field.label,
      stringValue(field.key, 'exchange value'),
    )
    const direction = stringValue(field.direction, 'both')
    const directionText =
      {
        sent: 'sent',
        received: 'received',
        both: 'sent and received',
        entry: 'declared for the entry',
      }[direction] ?? direction
    const tags = adifExchangeTags[stringValue(field.key)]
    const tagText =
      format === 'adif' && tags && direction !== 'entry'
        ? ` [ADIF: ${direction === 'sent' ? tags.sent : direction === 'received' ? tags.received : `${tags.sent} / ${tags.received}`}]`
        : ''
    return `${label} (${directionText})${tagText}${formatValueConstraints(field)}`
  })
  return ` Required contest exchange fields and constraints${condition ? ` when ${condition}` : ''}: ${entries.join('; ')}.`
}

function describeLogSubmissionRequirements(
  ruleset: RulesetDraft,
  contest?: { name: string; slug: string },
): string[] {
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
    ? ` when ${describeCondition(eligibilityConfig.when)}`
    : ''
  const allowedBands = eligibility ? stringList(eligibility.allowed_bands) : []
  const allowedModes = eligibility ? stringList(eligibility.allowed_modes) : []
  const bandConstraint = (format: string) =>
    allowedBands.length
      ? `Allowed band values${eligibilityCondition}: ${names(allowedBands, '')}; frequency values must fall within these bands.`
      : `No band restriction is configured; provide ${format === 'cabrillo' ? 'a Cabrillo frequency or band token' : 'an ADIF BAND or supported FREQ'} accepted by the importer.`
  const modeConstraint = (format: string) =>
    allowedModes.length
      ? `Allowed mode values${eligibilityCondition}: ${names(allowedModes, '')}.`
      : format === 'cabrillo'
        ? 'No contest mode restriction is configured; standard Cabrillo mode tokens include CW, PH, FM, RY, and DG.'
        : 'No contest mode restriction is configured; use the ADIF MODE or SUBMODE required by the sponsor.'
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
          ? `CONTEST must match “${contest.name}” or “${contest.slug}”`
          : 'CONTEST must match the selected contest'
        return `Required Cabrillo fields: START-OF-LOG: 2.0 or 3.0 and END-OF-LOG: records (the importer also accepts legacy unversioned markers); non-empty CALLSIGN and CONTEST headers (${contestHeader}); and, for every QSO, frequency or band, mode, date (UTC YYYY-MM-DD), time (UTC HHMM; the importer also accepts HHMMSS), sent callsign, sent RST, sent exchange, received callsign, received RST, and received exchange. Callsigns use A-Z, 0-9, or /; reports and exchange tokens must be non-empty. ${bandConstraint(format)} ${modeConstraint(format)}${exchangeDetails}`
      }
      return `Required ADIF fields: identify the station with STATION_CALLSIGN or OPERATOR in the header or a QSO record; every QSO record must end with <EOR> and include QSO_DATE (valid UTC date as YYYYMMDD), TIME_ON (HHMM or HHMMSS UTC), CALL (callsign), MODE or SUBMODE, BAND or FREQ in MHz, and sent and received exchange data. ${bandConstraint(format)} ${modeConstraint(format)}${exchangeDetails}`
    })
}

const categoryMeanings: Record<string, string> = {
  operator:
    'classifies the operator arrangement; the contest rules define operator eligibility, operating-time, and transmitter limits',
  power:
    'classifies station transmit power. QRP, Low Power, and High Power are labels, not universal wattage limits; the contest rules define exact output thresholds and where power is measured',
  band:
    'classifies all-band or single-band entry types; the contest rules define eligible bands and how band combinations are scored',
  mode: 'classifies operating modes; the contest rules define included modes and mixed-mode requirements',
  assisted:
    'indicates whether operating assistance is used; the contest rules define which tools count as assistance',
  transmitter:
    'classifies transmitter configuration; the contest rules define simultaneous transmitter and band-change limits',
  overlay:
    'is an additional sponsor-defined classification that may apply alongside a main category',
  station_class:
    'classifies station type or capability; the contest rules define location, portability, and equipment requirements',
  region:
    'groups entries by geography; the contest rules define the region boundaries and assignment source',
  category: 'is a sponsor-defined grouping of entries',
}

const powerChoiceMeanings: Record<string, string> = {
  qrp: 'Very-low-power class; the exact maximum output and measurement point vary by contest.',
  low: 'Low-power class; the exact maximum output and measurement point vary by contest.',
  high: 'High-power class; exact thresholds or ranges and the measurement point vary by contest.',
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

function categoryChoiceMeaning(dimensionKey: string, choice: JsonRecord): string {
  const customDescription = stringValue(choice.description)
  if (customDescription) return customDescription
  return dimensionKey === 'power'
    ? powerChoiceMeanings[stringValue(choice.key)] ?? ''
    : ''
}

function describeCondition(value: unknown): string {
  if (!isRecord(value)) return 'the configured condition'
  if (value.kind === 'compare') {
    const fact = stringValue(value.fact, 'configured contest value')
      .replace(/^qso\./, 'contact ')
      .replace(/^entry\./, 'entry ')
      .replace(/^station\./, 'station ')
      .replace(/^exchange\./, 'exchange ')
      .replaceAll('_', ' ')
    const operator = {
      eq: 'is',
      ne: 'is not',
      in: 'is one of',
      not_in: 'is not one of',
      lt: 'is less than',
      lte: 'is at most',
      gt: 'is greater than',
      gte: 'is at least',
      matches: 'matches',
      exists: 'is present',
    }[stringValue(value.operator)]
    if (value.operator === 'exists') return `${fact} ${operator}`
    const expected = Array.isArray(value.value)
      ? names(value.value.map(String), 'the configured values')
      : String(value.value ?? 'the configured value')
    return `${fact} ${operator ?? 'matches'} ${expected}`
  }
  if (value.kind === 'all' || value.kind === 'any') {
    const conditions = Array.isArray(value.conditions)
      ? value.conditions.map(describeCondition)
      : []
    return conditions.length
      ? conditions.join(value.kind === 'all' ? ' and ' : ' or ')
      : 'the configured conditions'
  }
  if (value.kind === 'not') {
    return `not (${describeCondition(value.condition)})`
  }
  return 'the configured condition'
}

function summarizeRule(rule: JsonRecord): string {
  switch (rule.kind) {
    case 'submission': {
      const latePolicy = {
        reject: 'Late logs are rejected.',
        accept_late: 'Late logs may be accepted and marked late.',
        checklog: 'Late logs are classified for checklog review.',
      }[stringValue(rule.late_policy)]
      return `${latePolicy ?? 'The late-log policy is defined by the contest.'}${
        rule.manager_extension_allowed === true
          ? ' A contest manager may extend the submission cutoff.'
          : ''
      }`
    }
    case 'categories': {
      const dimensionRows = Array.isArray(rule.dimensions)
        ? rule.dimensions.filter(isRecord)
        : []
      const dimensions = dimensionRows.map((dimension) => {
        const choiceRows = Array.isArray(dimension.choices)
          ? dimension.choices
              .filter(isRecord)
          : []
        const choices = choiceRows.map((choice) =>
          stringValue(choice.label, stringValue(choice.key)),
        )
        const key = stringValue(dimension.key)
        const label = stringValue(
          dimension.label,
          stringValue(dimension.key, 'Category'),
        )
        const dimensionKind = categoryDimensionKind(key, label)
        const requirement =
          dimension.required === false ? 'optional' : 'required'
        const meaning =
          stringValue(dimension.description) ||
          categoryMeanings[dimensionKind] ||
          'is a sponsor-defined classification; check the official rules for its exact definition and limits'
        const choiceDefinitions = choiceRows
          .map((choice) => {
            const meaning = categoryChoiceMeaning(dimensionKind, choice)
            return meaning
              ? `${stringValue(choice.label, stringValue(choice.key))}: ${meaning}`
              : ''
          })
          .filter(Boolean)
        const values = choices.length
          ? `: ${names(choices, '')}`
          : ''
        const choiceText = choiceDefinitions.length
          ? ` Choice details: ${choiceDefinitions.join('; ')}.`
          : ''
        return `${label} (${requirement})${values}. This ${meaning}.${choiceText}`
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
        return 'Entry categories are configured for this contest.'
      }
      const summary = `Categories divide entries into separate classification dimensions. Participants select one value for each required dimension; optional dimensions may be left blank. The dimension meanings and choices are: ${dimensions.join(' ')} Exact qualifications and limits are contest-specific; the official published rules are authoritative.`
      const declarationChoices = dimensionRows.flatMap((dimension) => {
        const dimensionLabel = stringValue(
          dimension.label,
          stringValue(dimension.key, 'Category'),
        )
        return Array.isArray(dimension.choices)
          ? dimension.choices
              .filter(isRecord)
              .filter((choice) => choice.requires_declaration === true)
              .map(
                (choice) =>
                  `${stringValue(choice.label, stringValue(choice.key, 'Category choice'))} in ${dimensionLabel}`,
              )
          : []
      })
      const declarationText = declarationChoices.length
        ? ` The ruleset marks ${names(declarationChoices, 'the marked choices')} as requiring a declaration.`
        : ''
      const exclusionText = exclusions.length
        ? ` These dimensions cannot be combined: ${exclusions
            .map((group) => names(group, 'configured dimensions'))
            .join('; ')}.`
        : ''
      return `${summary}${declarationText}${exclusionText}`
    }
    case 'exchange': {
      const fields = Array.isArray(rule.fields)
        ? rule.fields.filter(isRecord).map((field) => {
            const label = stringValue(
              field.label,
              stringValue(field.key, 'exchange value'),
            )
            const direction = stringValue(field.direction)
            const directionText = {
              sent: 'sent',
              received: 'received',
              both: 'sent and received',
              entry: 'declared for the entry',
            }[direction]
            return directionText ? `${label} (${directionText})` : label
          })
        : []
      return fields.length
        ? `Stations exchange ${names(fields, 'the configured exchange fields')}.`
        : 'Stations use the exchange fields configured for this contest.'
    }
    case 'eligibility': {
      const bands = stringList(rule.allowed_bands)
      const modes = stringList(rule.allowed_modes)
      const limits = [
        bands.length ? `bands ${names(bands, '')}` : 'all bands',
        modes.length ? `modes ${names(modes, '')}` : 'all modes',
      ]
      const checks = [
        rule.reject_self_contacts === true ? 'self-contacts are excluded' : '',
        rule.reject_out_of_period === true
          ? 'contacts outside the contest period are excluded'
          : '',
        rule.reject_missing_required_exchange === true
          ? 'contacts missing required exchange details are excluded'
          : '',
        rule.eligible_if !== undefined && rule.eligible_if !== null
          ? 'additional configured contact conditions apply'
          : '',
      ].filter(Boolean)
      return `Eligible contacts may use ${names(limits, 'the configured operating limits')}.${
        checks.length ? ` ${names(checks, '')}.` : ''
      }`
    }
    case 'duplicates': {
      const scope = stringList(rule.scope).map(
        (item) =>
          ({
            worked_callsign: 'the same callsign',
            band: 'the same band',
            mode: 'the same mode',
            grid: 'the same grid square',
            transmitter: 'the same transmitter',
          })[item] ?? item,
      )
      const effect = {
        ignore: 'ignored',
        not_credited: 'not credited',
        penalty: 'subject to a penalty',
        needs_review: 'sent for review',
      }[stringValue(rule.effect)]
      return `A contact repeated with ${names(scope, 'the configured duplicate identity')} is ${effect ?? 'handled by the configured duplicate policy'}.`
    }
    case 'points': {
      const fact = stringValue(rule.fact)
      if (fact === 'fixed' && typeof rule.fixed_points === 'number') {
        return `Each eligible contact is worth ${rule.fixed_points} points.`
      }
      const values = isRecord(rule.values) ? Object.entries(rule.values) : []
      const examples = values
        .slice(0, 4)
        .map(([key, value]) => `${key}: ${String(value)} points`)
      const remainder =
        values.length > examples.length
          ? `, plus ${values.length - examples.length} other values`
          : ''
      const defaultPoints =
        typeof rule.default_points === 'number'
          ? ` Contacts without a matching value are worth ${rule.default_points} points.`
          : ''
      return examples.length
        ? `Contact points are based on ${fact || 'configured contact details'} (${examples.join('; ')}${remainder}).${defaultPoints}`
        : `Contact points are based on ${fact || 'the configured scoring rule'}.`
    }
    case 'multiplier': {
      const source = stringValue(
        rule.source_fact,
        'the configured exchange or contact value',
      )
      const scope = stringValue(rule.scope, 'contest')
      return `Multipliers come from ${source} and count once per ${scope.replaceAll('_', ' ')}.`
    }
    case 'bonus': {
      const points =
        typeof rule.points === 'number' ? rule.points : 'configured'
      const basis =
        rule.basis === 'per_entry' ? 'per entry' : 'per eligible contact'
      const cap =
        typeof rule.cap === 'number' ? `, up to ${rule.cap} points` : ''
      const minimum =
        typeof rule.minimum_eligible_qsos === 'number' &&
        rule.minimum_eligible_qsos > 0
          ? ` after at least ${rule.minimum_eligible_qsos} eligible contacts`
          : ''
      const evidence =
        typeof rule.evidence_key === 'string'
          ? ` Evidence declaration “${rule.evidence_key}” is required.`
          : ''
      return `Bonus: ${points} points ${basis}${cap}${minimum}.${evidence}`
    }
    case 'penalty': {
      const action = stringValue(
        rule.action,
        'the configured consequence',
      ).replaceAll('_', ' ')
      const points =
        typeof rule.points === 'number' && rule.points > 0
          ? ` (${rule.points} points)`
          : ''
      const maximum =
        typeof rule.maximum_occurrences === 'number' &&
        rule.maximum_occurrences > 1
          ? `, up to ${rule.maximum_occurrences} times`
          : ''
      return `For ${stringValue(rule.reason_code, 'a configured violation')}, the penalty is to ${action}${points}${maximum}.`
    }
    case 'score_formula': {
      const variableNames: Record<string, string> = {
        points_total: 'contact points',
        multiplier_count: 'multipliers',
        bonus_points: 'bonus points',
        penalty_points: 'penalty points',
        power_multiplier: 'power multiplier',
      }
      const operand = (value: unknown) => {
        if (!isRecord(value)) return 'a configured value'
        if (typeof value.constant === 'number') return String(value.constant)
        return (
          variableNames[stringValue(value.variable)] ?? 'a configured value'
        )
      }
      const operators: Record<string, string> = {
        add: 'plus',
        subtract: 'minus',
        multiply: 'multiplied by',
        floor_divide: 'divided by',
        round_divide: 'divided by',
      }
      const steps = Array.isArray(rule.steps) ? rule.steps.filter(isRecord) : []
      const expression = [
        operand(rule.start),
        ...steps.map((step) => {
          const rounding =
            step.operator === 'round_divide' &&
            typeof step.rounding === 'string'
              ? ` (${step.rounding.replaceAll('_', ' ')} rounding)`
              : ''
          return `${operators[stringValue(step.operator)] ?? 'combined with'} ${operand(step.operand)}${rounding}`
        }),
      ]
      return `Final score: ${expression.join(' ')}. Scores use whole-number points.`
    }
    case 'operating_constraints': {
      const limits = [
        typeof rule.max_operating_minutes === 'number' &&
          `up to ${rule.max_operating_minutes} operating minutes`,
        typeof rule.maximum_band_changes === 'number' &&
          `up to ${rule.maximum_band_changes} band changes`,
        typeof rule.maximum_transmitters === 'number' &&
          `up to ${rule.maximum_transmitters} transmitters`,
        typeof rule.minimum_off_time_minutes === 'number' &&
          rule.minimum_off_time_minutes > 0 &&
          `${rule.minimum_off_time_minutes} minutes of off time`,
        typeof rule.required_off_periods === 'number' &&
          rule.required_off_periods > 0 &&
          `${rule.required_off_periods} required off periods`,
        typeof rule.minimum_band_dwell_minutes === 'number' &&
          `${rule.minimum_band_dwell_minutes}-minute minimum band dwell`,
        rule.one_transmitted_signal_per_band === true &&
          'one transmitted signal per band',
      ].filter((item): item is string => typeof item === 'string')
      return limits.length
        ? `Operating limits include ${names(limits, 'the configured station rules')}.`
        : 'Operating and station limits follow the contest configuration.'
    }
    case 'format_mapping':
      return `${stringValue(rule.format, 'The configured')} log format is accepted.${
        rule.preserve_unknown_fields === true
          ? ' Unrecognized fields are retained for review.'
          : ''
      }`
    case 'workflow_hook': {
      const stage = stringValue(rule.stage, 'contest')
      const execution = {
        automatic: 'runs automatically',
        declaration: 'uses participant declarations',
        human_review: 'requires human review',
      }[stringValue(rule.execution)]
      return `${stage.charAt(0).toUpperCase()}${stage.slice(1)} processing ${execution ?? 'follows the configured workflow'}.`
    }
    default:
      return `Additional contest rule configured: ${stringValue(rule.kind, 'unspecified')}.`
  }
}

export function describeContestRuleset(
  ruleset: RulesetDraft | null,
  contest?: { name: string; slug: string },
): string[] {
  if (!ruleset || !Array.isArray(ruleset.rules)) return []
  const descriptions = ruleset.rules.flatMap((configured) => {
    if (!isRecord(configured) || !isRecord(configured.rule)) return []
    const summary = summarizeRule(configured.rule)
    return [
      configured.when === undefined || configured.when === null
        ? summary
        : `Only when ${describeCondition(configured.when)}: ${summary.charAt(0).toLowerCase()}${summary.slice(1)}`,
    ]
  })
  return [
    ...descriptions,
    ...describeLogSubmissionRequirements(ruleset, contest),
  ]
}
