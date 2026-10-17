import { describe, expect, it } from 'vitest'
import {
  describeContestRuleset,
  generateCabrilloExample,
  type ContestSummaryItem,
} from './publicContestDescription'
import { setLocale, supportedLocales } from '../i18n'

function summaryText(item: ContestSummaryItem): string {
  return typeof item === 'string'
    ? item
    : [item.introduction, ...item.bullets, ...(item.notes ?? [])].join(' ')
}

function summaryIntroduction(item: ContestSummaryItem): string {
  return typeof item === 'string' ? item : item.introduction
}

describe('describeContestRuleset', () => {
  it('generates a two-QSO Cabrillo sample using the contest ruleset', () => {
    const sample = generateCabrilloExample(
      {
        schema_version: 2,
        ruleset_key: 'sample-cabrillo',
        version: '2026',
        rules: [
          {
            id: 'eligibility',
            rule: {
              kind: 'eligibility',
              allowed_bands: ['40m'],
              allowed_modes: ['CW'],
            },
          },
          {
            id: 'exchange',
            rule: {
              kind: 'exchange',
              fields: [
                { key: 'serial', direction: 'both', value_type: 'serial' },
              ],
            },
          },
          {
            id: 'categories',
            rule: {
              kind: 'categories',
              dimensions: [
                {
                  key: 'power',
                  label: 'Power',
                  choices: [{ key: 'low', label: 'Low power' }],
                },
              ],
            },
          },
          {
            id: 'format',
            rule: {
              kind: 'format_mapping',
              format: 'cabrillo',
              category_mappings: [
                {
                  external_value: 'LOW',
                  category_values: { power: 'low' },
                },
              ],
            },
          },
        ],
      },
      {
        name: 'Autumn Test',
        slug: 'autumn-test',
        starts_at: '2026-10-20T00:00:00Z',
        ends_at: '2026-10-20T06:00:00Z',
      },
    )

    expect(sample).not.toBeNull()
    expect(sample).toContain('START-OF-LOG: 3.0')
    expect(sample).toContain('CONTEST: autumn-test')
    expect(sample).toContain('CALLSIGN: N0TEST')
    expect(sample).toContain('CATEGORY-POWER: LOW')
    expect(sample?.match(/^QSO:/gm)).toHaveLength(2)
    expect(sample).toContain(
      'QSO: 7040 CW 2026-10-20 0000 N0TEST 599 001 K1ABC 599 033',
    )
    expect(sample).toContain(
      'QSO: 7040 CW 2026-10-20 0000 N0TEST 599 002 W1XYZ 599 034',
    )
    expect(sample?.endsWith('END-OF-LOG:')).toBe(true)
  })

  it('omits the Cabrillo sample when the contest accepts another format only', () => {
    expect(
      generateCabrilloExample(
        {
          schema_version: 2,
          ruleset_key: 'sample-adif',
          version: '2026',
          rules: [
            { id: 'format', rule: { kind: 'format_mapping', format: 'adif' } },
          ],
        },
        {
          name: 'ADIF Test',
          slug: 'adif-test',
          starts_at: '2026-10-20T00:00:00Z',
          ends_at: '2026-10-20T06:00:00Z',
        },
      ),
    ).toBeNull()
  })

  it('generates separate category headers and a transmitter field for multi-category contests', () => {
    const columns = [
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
      'transmitter',
    ]
    const categories = [
      ['operator', 'multi', 'MULTI-OP'],
      ['power', 'low', 'LOW'],
      ['band_class', 'all_bands', 'ALL'],
      ['mode', 'cw', 'CW'],
      ['transmitter_count', 'two', 'TWO'],
    ] as const
    const sample = generateCabrilloExample(
      {
        schema_version: 2,
        ruleset_key: 'multi-category-cabrillo',
        version: '2026',
        rules: [
          {
            id: 'eligibility',
            rule: {
              kind: 'eligibility',
              allowed_bands: ['20m', '40m'],
              allowed_modes: ['CW'],
            },
          },
          {
            id: 'exchange',
            rule: {
              kind: 'exchange',
              fields: [
                {
                  key: 'serial',
                  direction: 'both',
                  value_type: 'serial',
                },
              ],
            },
          },
          {
            id: 'categories',
            rule: {
              kind: 'categories',
              dimensions: categories.map(([key, choice]) => ({
                key,
                label: key,
                required: true,
                choices: [{ key: choice }],
              })),
            },
          },
          {
            id: 'format',
            rule: {
              kind: 'format_mapping',
              format: 'cabrillo',
              qso_columns: columns,
              category_mappings: categories.map(
                ([key, choice, external_value]) => ({
                  external_value,
                  category_values: { [key]: choice },
                }),
              ),
            },
          },
        ],
      },
      {
        name: 'Multi Category Test',
        slug: 'multi-category-test',
        starts_at: '2026-10-20T00:00:00Z',
        ends_at: '2026-10-20T06:00:00Z',
      },
    )

    expect(sample).not.toBeNull()
    expect(sample).toContain('CATEGORY-OPERATOR: MULTI-OP')
    expect(sample).toContain('CATEGORY-POWER: LOW')
    expect(sample).toContain('CATEGORY-BAND: ALL')
    expect(sample).toContain('CATEGORY-MODE: CW')
    expect(sample).toContain('CATEGORY-TRANSMITTER: TWO')
    expect(sample?.match(/^QSO:/gm)).toHaveLength(2)
    expect(sample?.match(/ 1$/gm)).toHaveLength(2)
  })

  it('localizes generated rules and keeps dynamic scoring values in every locale', async () => {
    const ruleset = {
      schema_version: 2 as const,
      ruleset_key: 'translated-summary',
      version: '2026',
      rules: [
        {
          id: 'points',
          rule: { kind: 'points', fact: 'fixed', fixed_points: 37 },
        },
      ],
    }

    for (const locale of supportedLocales) {
      await setLocale(locale, undefined)
      const [description] = describeContestRuleset(ruleset)
      expect(description).toBeDefined()
      expect(description).toContain('37')
      if (locale !== 'en')
        expect(description).not.toBe(
          'Each eligible contact is worth 37 points.',
        )
    }
    await setLocale('en', undefined)
  })

  it('translates Cabrillo requirements while preserving standard tokens and contest values', async () => {
    const ruleset = {
      schema_version: 2 as const,
      ruleset_key: 'translated-cabrillo',
      version: '2026',
      rules: [
        {
          id: 'format',
          rule: { kind: 'format_mapping', format: 'cabrillo' },
        },
      ],
    }

    for (const locale of supportedLocales) {
      await setLocale(locale, undefined)
      const requirements = describeContestRuleset(ruleset, {
        name: 'Autumn Test',
        slug: 'autumn-test',
      }).at(-1)
      expect(requirements && typeof requirements !== 'string').toBe(true)
      if (!requirements || typeof requirements === 'string')
        throw new Error('Expected Cabrillo requirement bullets')
      const bullets = requirements.bullets.join(' ')
      for (const token of [
        'START-OF-LOG',
        'END-OF-LOG',
        'CALLSIGN',
        'CONTEST',
        'Autumn Test',
        'autumn-test',
        'YYYY-MM-DD',
        'HHMM',
        'RST',
      ]) {
        expect(bullets).toContain(token)
      }
      if (locale !== 'en')
        expect(requirements.introduction).not.toBe('Required Cabrillo fields:')
    }
    await setLocale('en', undefined)
  })

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

    expect(summaryText(descriptions[0]!)).toContain('operator arrangement')
    expect(summaryText(descriptions[0]!)).toContain(
      'Single operator and Multi operator',
    )
    expect(summaryText(descriptions[0]!)).toContain(
      'official published rules are authoritative',
    )
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
                  { key: 'qrp', label: 'QRP' },
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

    expect(summaryText(descriptions[0]!)).toContain('operator arrangement')
    expect(summaryText(descriptions[0]!)).toContain(
      'Single operator and Multi operator',
    )
    const powerSummary = summaryText(descriptions[0]!)
    expect(powerSummary).toContain('QRP: Maximum transmit output: 5 W.')
    expect(powerSummary).toContain('Low power: Maximum transmit output: 100 W.')
    expect(powerSummary).toContain(
      'High power: Maximum transmit output: up to the applicable legal limit.',
    )
    expect(
      powerSummary.match(/Unless contest rules specify otherwise/g),
    ).toHaveLength(1)
    expect(
      powerSummary.lastIndexOf('Unless contest rules specify otherwise'),
    ).toBeGreaterThan(
      powerSummary.indexOf('High power: Maximum transmit output'),
    )
    expect(summaryText(descriptions[0]!)).toContain(
      'Multi operator in Operator class as requiring a declaration',
    )
    expect(summaryText(descriptions[0]!)).toContain(
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
                description:
                  'Measured at the antenna connector after the amplifier.',
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

    expect(summaryText(descriptions[0]!)).toContain(
      'Measured at the antenna connector after the amplifier.',
    )
    expect(summaryText(descriptions[0]!)).toContain(
      'Low power: Maximum 100 W PEP at the antenna connector.',
    )
    expect(summaryText(descriptions[0]!)).toContain(
      'official published rules are authoritative',
    )
    expect(summaryText(descriptions[0]!)).not.toContain(
      'Unless contest rules specify otherwise',
    )
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

    expect(summaryText(descriptions[0]!)).toContain(
      'This is a sponsor-defined classification; check the official rules for its exact definition and limits.',
    )
  })

  it('lists required Cabrillo fields, contest values, and required exchange constraints', () => {
    const descriptions = describeContestRuleset({
      schema_version: 2,
      ruleset_key: 'cabrillo-fields',
      version: '1',
      rules: [
        {
          id: 'eligibility',
          rule: {
            kind: 'eligibility',
            allowed_bands: ['20m', '40m'],
            allowed_modes: ['CW'],
          },
        },
        {
          id: 'exchange',
          rule: {
            kind: 'exchange',
            fields: [
              {
                key: 'serial',
                label: 'Serial number',
                value_type: 'serial',
                direction: 'both',
                required: true,
                max_length: 6,
              },
              {
                key: 'section',
                label: 'Section',
                value_type: 'enum',
                direction: 'received',
                required: true,
                choices: ['A', 'B'],
              },
              {
                key: 'optional',
                label: 'Optional note',
                direction: 'entry',
                required: false,
              },
            ],
          },
        },
        {
          id: 'format',
          rule: { kind: 'format_mapping', format: 'cabrillo' },
        },
      ],
    })

    const requirements = descriptions.at(-1)
    expect(typeof requirements).not.toBe('string')
    if (!requirements || typeof requirements === 'string')
      throw new Error('Expected Cabrillo list')
    expect(requirements.introduction).toBe('Required Cabrillo fields:')
    expect(requirements.bullets).toContain(
      'START-OF-LOG: 2.0 or 3.0. The importer also accepts legacy unversioned markers.',
    )
    expect(requirements.bullets).toContain(
      'END-OF-LOG: terminates the log records.',
    )
    expect(requirements.bullets).toContain(
      'CALLSIGN: non-empty header value. CONTEST: non-empty header value; CONTEST must match the selected contest.',
    )
    expect(requirements.bullets).toContain(
      'Each QSO must include date in UTC as YYYY-MM-DD.',
    )
    expect(requirements.bullets).toContain(
      'Allowed band values: 20m and 40m; frequency values must fall within these bands.',
    )
    expect(requirements.bullets).toContain('Allowed mode values: CW.')
    expect(requirements.bullets).toContain(
      'Required exchange: Serial number (sent and received) (positive integer serial number; up to 6 characters).',
    )
    expect(requirements.bullets).toContain(
      'Required exchange: Section (received) (allowed values: A and B).',
    )
    expect(requirements.bullets.join(' ')).not.toContain('Optional note')
  })

  it('lists required ADIF tags, format alternatives, and only enabled formats', () => {
    const descriptions = describeContestRuleset({
      schema_version: 2,
      ruleset_key: 'adif-fields',
      version: '1',
      rules: [
        {
          id: 'exchange',
          rule: {
            kind: 'exchange',
            fields: [
              {
                key: 'serial',
                label: 'Serial number',
                value_type: 'serial',
                direction: 'both',
                required: true,
                min_integer: 1,
                max_integer: 999,
              },
              {
                key: 'grid',
                label: 'Grid square',
                value_type: 'grid',
                direction: 'received',
                required: true,
                pattern: '^[A-R]{2}[0-9]{2}$',
              },
            ],
          },
        },
        { id: 'adif', rule: { kind: 'format_mapping', format: 'adif' } },
        { id: 'csv', rule: { kind: 'format_mapping', format: 'csv' } },
      ],
    })

    const requirements = descriptions.at(-1) ?? ''
    expect(requirements).toContain('Required ADIF fields: identify the station')
    expect(requirements).toContain('STATION_CALLSIGN or OPERATOR')
    expect(requirements).toContain(
      'QSO_DATE (valid UTC date as YYYYMMDD), TIME_ON (HHMM or HHMMSS UTC)',
    )
    expect(requirements).toContain('MODE or SUBMODE, BAND or FREQ')
    expect(requirements).toContain(
      'Serial number (sent and received) [ADIF: STX or STX_STRING / SRX or SRX_STRING]',
    )
    expect(requirements).toContain('integer from 1 to 999')
    expect(requirements).toContain(
      'Grid square (received) [ADIF: GRIDSQUARE] (must match ^[A-R]{2}[0-9]{2}$; grid locator)',
    )
    expect(requirements).not.toContain('CSV')
    expect(requirements).not.toContain('Required Cabrillo fields')
  })

  it('includes separate requirements when both Cabrillo and ADIF are accepted', () => {
    const descriptions = describeContestRuleset({
      schema_version: 2,
      ruleset_key: 'both-formats',
      version: '1',
      rules: [
        {
          id: 'cabrillo',
          rule: { kind: 'format_mapping', format: 'cabrillo' },
        },
        { id: 'adif', rule: { kind: 'format_mapping', format: 'adif' } },
      ],
    })

    expect(
      descriptions.filter((description) =>
        summaryIntroduction(description).startsWith('Required '),
      ),
    ).toHaveLength(2)
    expect(
      descriptions.some((description) =>
        summaryIntroduction(description).startsWith('Required Cabrillo'),
      ),
    ).toBe(true)
    expect(
      descriptions.some((description) =>
        summaryIntroduction(description).startsWith('Required ADIF'),
      ),
    ).toBe(true)
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
