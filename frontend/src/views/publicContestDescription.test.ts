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

    expect(descriptions).toEqual([
      'Categories divide entries into separate classification dimensions. Participants select one value for each required dimension; optional dimensions may be left blank: Operator (required): Single operator and Multi operator.',
      'Stations exchange Serial number (sent and received) and Section (received).',
      'Only when contact band is 20m: final score: contact points multiplied by multipliers plus bonus points. Scores use whole-number points.',
    ])
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

    expect(descriptions).toEqual([
      'Categories divide entries into separate classification dimensions. Participants select one value for each required dimension; optional dimensions may be left blank: Operator class (required): Single operator and Multi operator; Power class (optional): Low power and High power. The ruleset marks Multi operator in Operator class as requiring a declaration. These dimensions cannot be combined: Operator class and Power class.',
    ])
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
