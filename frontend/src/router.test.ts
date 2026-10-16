import { describe, expect, it } from 'vitest'
import { router } from './router'

describe('management routes', () => {
  it('separates contest and ruleset listings from their create and edit pages', () => {
    expect(router.resolve('/manage/contests').name).toBe('contest-manager')
    expect(router.resolve('/manage/contests/new').name).toBe('contest-create')
    expect(router.resolve('/manage/contests/42/edit').name).toBe('contest-edit')
    expect(router.resolve('/manage/rulesets').name).toBe('ruleset-manager')
    expect(router.resolve('/manage/rulesets/new').name).toBe('ruleset-create')
    expect(router.resolve('/manage/rulesets/21/edit').name).toBe('ruleset-edit')
  })

  it('redirects old ruleset composer URLs to the ruleset list or editor', () => {
    expect(
      router.resolve('/rulesets/compose').matched.at(-1)?.redirect,
    ).toBeDefined()
    expect(
      router.resolve('/rulesets/compose/21').matched.at(-1)?.redirect,
    ).toBeDefined()
  })
})
