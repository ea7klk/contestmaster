import { describe, expect, it } from 'vitest'
import { describeContestRuleset } from './publicContestDescription'

describe('describeContestRuleset', () => {
  it('turns common scoring and exchange rules into plain-language descriptions', () => {
    const descriptions = describeContestRuleset({
      schema_version: 2,
      ruleset_key: 'sample',
      version: '2026',
      rules: [
        {
          id: 'categories',
          rule: {
            kind: 'categories',
            dimensions: [
              {
                key: 'operator',
                label: 'Operator',
                choices: [
                  { key: 'single', label: 'Single operator' },
                  { key: 'multi', label: 'Multi operator' },
                ],
              },
            ],
          },
        },
        {
          id: 'exchange',
          rule: {
            kind: 'exchange',
            fields: [
              { key: 'serial', label: 'Serial number', direction: 'both' },
              { key: 'section', label: 'Section', direction: 'received' },
            ],
          },
        },
        {
          id: 'score',
          rule: {
            kind: 'score_formula',
            start: { variable: 'points_total' },
            steps: [
              {
                operator: 'multiply',
                operand: { variable: 'multiplier_count' },
              },
              { operator: 'add', operand: { variable: 'bonus_points' } },
            ],
          },
          when: {
            kind: 'compare',
            fact: 'qso.band',
            operator: 'eq',
            value: '20m',
          },
        },
      ],
    })

    expect(descriptions[0]).toContain('operator arrangement')
    expect(descriptions[0]).toContain('Single operator and Multi operator')
    expect(descriptions[0]).toContain('official published rules are authoritative')
    expect(descriptions[1]).toBe(
      'Stations exchange Serial number (sent and received) and Section (received).',
    )
    expect(descriptions[2]).toBe(
      'Only when contact band is 20m: final score: contact points multiplied by multipliers plus bonus points. Scores use whole-number points.',
    )
  })

  it('explains category segmentation, required choices, declarations, and exclusions', () => {
    const descriptions = describeContestRuleset({
      schema_version: 2,
      ruleset_key: 'segmented-sprint',
      version: '2026',
      rules: [
        {
          id: 'categories',
          rule: {
            kind: 'categories',
            dimensions: [
              {
                key: 'operator',
                label: 'Operator class',
                required: true,
                choices: [
                  { key: 'single', label: 'Single operator' },
                  {
                    key: 'multi',
                    label: 'Multi operator',
                    requires_declaration: true,
                  },
                ],
              },
              {
                key: 'power',
                label: 'Power class',
                required: false,
                choices: [
                  { key: 'low', label: 'Low power' },
                  { key: 'high', label: 'High power' },
                ],
              },
            ],
            mutually_exclusive: [['operator', 'power']],
          },
        },
      ],
    })

    expect(descriptions[0]).toContain('operator arrangement')
    expect(descriptions[0]).toContain('Single operator and Multi operator')
    expect(descriptions[0]).toContain('not universal wattage limits')
    expect(descriptions[0]).toContain('Low-power class; the exact maximum output')
    expect(descriptions[0]).toContain(
      'Multi operator in Operator class as requiring a declaration',
    )
    expect(descriptions[0]).toContain(
      'These dimensions cannot be combined: Operator class and Power class.',
    )
  })

  it('uses ruleset-authored dimension and choice explanations in contest details', () => {
    const descriptions = describeContestRuleset({
      schema_version: 2,
      ruleset_key: 'custom-power',
      version: '1',
      rules: [
        {
          id: 'categories',
          rule: {
            kind: 'categories',
            dimensions: [
              {
                key: 'power',
                label: 'Output class',
                description: 'Measured at the antenna connector after the amplifier.',
                choices: [
                  {
                    key: 'low',
                    label: 'Low power',
                    description: 'Maximum 100 W PEP at the antenna connector.',
                  },
                ],
              },
            ],
          },
        },
      ],
    })

    expect(descriptions[0]).toContain(
      'Measured at the antenna connector after the amplifier.',
    )
    expect(descriptions[0]).toContain(
      'Low power: Maximum 100 W PEP at the antenna connector.',
    )
    expect(descriptions[0]).toContain('official published rules are authoritative')
  })

  it('identifies custom categories as sponsor-defined when no explanation is saved', () => {
    const descriptions = describeContestRuleset({
      schema_version: 2,
      ruleset_key: 'custom-class',
      version: '1',
      rules: [
        {
          id: 'categories',
          rule: {
            kind: 'categories',
            dimensions: [
              {
                key: 'junior_class',
                label: 'Junior class',
                choices: [{ key: 'junior', label: 'Junior' }],
              },
            ],
          },
        },
      ],
    })

    expect(descriptions[0]).toContain(
      'This is a sponsor-defined classification; check the official rules for its exact definition and limits.',
    )
  })

  it('handles absent and unknown rule types without crashing or inventing semantics', () => {
    expect(describeContestRuleset(null)).toEqual([])
    expect(
      describeContestRuleset({
        schema_version: 2,
        ruleset_key: 'future',
        version: '1',
        rules: [
          { id: 'new', rule: { kind: 'future_rule' } },
          {
            id: 'broken',
            rule: 'not a rule' as unknown as Record<string, unknown>,
          },
        ],
      }),
    ).toEqual(['Additional contest rule configured: future_rule.'])
  })
})
