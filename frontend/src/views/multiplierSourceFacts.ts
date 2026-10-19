export interface MultiplierFactRule {
  rule: Record<string, unknown>
}

export interface MultiplierFactOption {
  value: string
  label: string
}

export function availableMultiplierSourceFacts(
  rules: MultiplierFactRule[],
): MultiplierFactOption[] {
  const facts: MultiplierFactOption[] = [
    { value: 'qso.id', label: 'QSO ID' },
    { value: 'qso.occurred_at', label: 'QSO timestamp' },
    { value: 'qso.worked_callsign', label: 'Worked callsign' },
    { value: 'qso.wpx_prefix', label: 'WPX-style prefix from worked callsign' },
    { value: 'qso.callsign_suffix', label: 'Suffix from worked callsign' },
    { value: 'qso.band', label: 'Band' },
    { value: 'qso.mode', label: 'Mode' },
    { value: 'qso.grid', label: 'Grid locator' },
    { value: 'qso.transmitter', label: 'Transmitter' },
    { value: 'qso.continent', label: 'Continent' },
    { value: 'qso.entity', label: 'Worked station entity (CTY)' },
    { value: 'qso.cq_zone', label: 'CQ zone' },
    { value: 'qso.itu_zone', label: 'ITU zone' },
    { value: 'entry.id', label: 'Entry ID' },
    { value: 'entry.power_multiplier', label: 'Power multiplier' },
  ]
  const exchangeRule = rules.find((item) => item.rule.kind === 'exchange')?.rule
  const fields = Array.isArray(exchangeRule?.fields)
    ? (exchangeRule.fields as Array<Record<string, unknown>>)
    : []

  for (const field of fields) {
    if (typeof field.key !== 'string') continue
    const direction = String(field.direction ?? 'both')
    const label = typeof field.label === 'string' ? field.label : field.key
    if (direction === 'received' || direction === 'both') {
      facts.push({
        value: `exchange.${field.key}`,
        label: `${label} — received (exchange.${field.key})`,
      })
      facts.push({
        value: `exchange.received.${field.key}`,
        label: `${label} — received (exchange.received.${field.key})`,
      })
    }
    if (direction === 'sent' || direction === 'both') {
      facts.push({
        value: `exchange.sent.${field.key}`,
        label: `${label} — sent (exchange.sent.${field.key})`,
      })
    }
    if (direction === 'entry') {
      facts.push({
        value: `exchange.entry.${field.key}`,
        label: `${label} — entry exchange (exchange.entry.${field.key})`,
      })
      facts.push({
        value: `entry.declarations.${field.key}`,
        label: `${label} — entry declaration (entry.declarations.${field.key})`,
      })
    }
  }

  const categoryRule = rules.find(
    (item) => item.rule.kind === 'categories',
  )?.rule
  const dimensions = Array.isArray(categoryRule?.dimensions)
    ? (categoryRule.dimensions as Array<Record<string, unknown>>)
    : []
  for (const dimension of dimensions) {
    if (typeof dimension.key !== 'string') continue
    const label =
      typeof dimension.label === 'string' ? dimension.label : dimension.key
    facts.push({
      value: `entry.categories.${dimension.key}`,
      label: `${label} category (entry.categories.${dimension.key})`,
    })
  }

  return [...new Map(facts.map((fact) => [fact.value, fact])).values()]
}
