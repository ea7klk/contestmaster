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
      const dimensions = Array.isArray(rule.dimensions)
        ? rule.dimensions.filter(isRecord).map((dimension) => {
            const choices = Array.isArray(dimension.choices)
              ? dimension.choices
                  .filter(isRecord)
                  .map((choice) =>
                    stringValue(choice.label, stringValue(choice.key)),
                  )
              : []
            const label = stringValue(
              dimension.label,
              stringValue(dimension.key, 'Category'),
            )
            const optional = dimension.required === false ? ' (optional)' : ''
            return choices.length
              ? `${label}${optional}: ${names(choices, '')}`
              : `${label}${optional}`
          })
        : []
      return dimensions.length
        ? `Entries are classified by ${names(dimensions, 'the configured categories')}.`
        : 'Entry categories are configured for this contest.'
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
      return `Log submissions use ${stringValue(rule.format, 'the configured')} format.${
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

export function describeContestRuleset(ruleset: RulesetDraft | null): string[] {
  if (!ruleset || !Array.isArray(ruleset.rules)) return []
  return ruleset.rules.flatMap((configured) => {
    if (!isRecord(configured) || !isRecord(configured.rule)) return []
    const summary = summarizeRule(configured.rule)
    return [
      configured.when === undefined || configured.when === null
        ? summary
        : `Only when ${describeCondition(configured.when)}: ${summary.charAt(0).toLowerCase()}${summary.slice(1)}`,
    ]
  })
}
