import { describe, expect, it } from 'vitest'
import { availableMultiplierSourceFacts } from './multiplierSourceFacts'

describe('availableMultiplierSourceFacts', () => {
  it('combines built-in, category, declaration, and direction-valid exchange facts', () => {
    const facts = availableMultiplierSourceFacts([
      {
        rule: {
          kind: 'categories',
          dimensions: [{ key: 'power', label: 'Power' }],
        },
      },
      {
        rule: {
          kind: 'exchange',
          fields: [
            { key: 'section', label: 'Section', direction: 'received' },
            { key: 'serial', label: 'Serial', direction: 'both' },
            {
              key: 'operator_class',
              label: 'Operator class',
              direction: 'entry',
            },
            { key: 'sent_only', direction: 'sent' },
          ],
        },
      },
    ])
    const paths = facts.map((fact) => fact.value)

    expect(paths).toContain('qso.entity')
    expect(paths).toContain('station.entity')
    expect(paths).toContain('station.continent')
    expect(paths).toContain('qso.wpx_prefix')
    expect(paths).toContain('qso.callsign_suffix')
    expect(paths).toContain('entry.categories.power')
    expect(paths).toContain('exchange.section')
    expect(paths).toContain('exchange.received.section')
    expect(paths).toContain('exchange.serial')
    expect(paths).toContain('exchange.sent.serial')
    expect(paths).toContain('exchange.received.serial')
    expect(paths).toContain('exchange.entry.operator_class')
    expect(paths).toContain('entry.declarations.operator_class')
    expect(paths).toContain('exchange.sent.sent_only')
    expect(paths).not.toContain('exchange.sent.section')
    expect(paths).not.toContain('exchange.received.sent_only')
    expect(new Set(paths).size).toBe(paths.length)
  })
})
