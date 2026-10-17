<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { ApiError } from '../api/client'
import { getPublicContest, type PublicContestDetails } from '../api/results'
import { formatUtcDateTime, i18n } from '../i18n'
import { renderContestMarkdown } from './contestMarkdown'
import {
  describeContestRuleset,
  generateCabrilloExample,
  type ContestSummaryItem,
  type SummaryWithBullets,
} from './publicContestDescription'

const props = defineProps<{ slug: string }>()
const contest = ref<PublicContestDetails | null>(null)
const loading = ref(true)
const error = ref('')
const rulesetSummary = computed(() => {
  // Rebuild the generated prose when the user changes the interface language.
  void i18n.global.locale.value
  return describeContestRuleset(
    contest.value?.ruleset ?? null,
    contest.value
      ? { name: contest.value.name, slug: contest.value.slug }
      : undefined,
  )
})
const cabrilloExample = computed(() => {
  const current = contest.value
  if (!current) return null
  return generateCabrilloExample(current.ruleset ?? null, {
    name: current.name,
    slug: current.slug,
    starts_at: current.starts_at,
    ends_at: current.ends_at,
  })
})
function hasBullets(item: ContestSummaryItem): item is SummaryWithBullets {
  return typeof item !== 'string'
}
const contestDescriptionHtml = computed(() =>
  renderContestMarkdown(contest.value?.description ?? null),
)

function formatUtc(value: string) {
  return formatUtcDateTime(value)
}

const acceptsLogs = () =>
  contest.value?.status === 'open' &&
  Date.parse(contest.value.log_submission_cutoff_at) > Date.now()

onMounted(async () => {
  try {
    contest.value = await getPublicContest(props.slug)
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'Contest details could not be loaded.'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section
    class="form-card public-contest"
    aria-labelledby="public-contest-title"
  >
    <p class="eyebrow">{{ $tr('Public contest details') }}</p>
    <p v-if="loading" role="status" class="notice">
      {{ $tr('Loading contest details…') }}
    </p>
    <p v-else-if="error" role="alert" class="error-panel">{{ $tr(error) }}</p>
    <template v-else-if="contest">
      <h1 id="public-contest-title">{{ contest.name }}</h1>
      <!-- HTML is parsed and sanitized in contestMarkdown.ts before rendering. -->
      <!-- eslint-disable vue/no-v-html -->
      <section
        v-if="contestDescriptionHtml"
        class="contest-description markdown-content"
        :aria-label="$tr('Contest description')"
        v-html="contestDescriptionHtml"
      />
      <!-- eslint-enable vue/no-v-html -->
      <section
        class="ruleset-overview"
        aria-labelledby="ruleset-overview-title"
      >
        <h2 id="ruleset-overview-title">
          {{ $tr('Contest rules at a glance') }}
        </h2>
        <p class="generated-summary-note">
          {{
            $tr(
              'This summary is automatically generated from the ruleset and may be imprecise. Refer to the contest’s official published rules for the authoritative requirements. The English version of this description remains authoritative.',
            )
          }}
        </p>
        <ul v-if="rulesetSummary.length">
          <li v-for="(item, index) in rulesetSummary" :key="index">
            <template v-if="hasBullets(item)">
              {{ item.introduction }}
              <ul class="summary-detail-list">
                <li
                  v-for="(bullet, bulletIndex) in item.bullets"
                  :key="bulletIndex"
                >
                  {{ bullet }}
                </li>
              </ul>
              <p v-for="(note, noteIndex) in item.notes" :key="noteIndex">
                {{ note }}
              </p>
            </template>
            <template v-else>{{ item }}</template>
          </li>
        </ul>
        <p v-else>{{ $tr('Detailed contest rules are not available yet.') }}</p>
        <section
          v-if="cabrilloExample"
          class="cabrillo-example"
          aria-labelledby="cabrillo-example-title"
        >
          <h3 id="cabrillo-example-title">
            Cabrillo example with two valid QSO lines
          </h3>
          <pre><code>{{ cabrilloExample }}</code></pre>
        </section>
      </section>
      <dl class="contest-dates">
        <div>
          <dt>{{ $tr('Contest start') }}</dt>
          <dd>{{ formatUtc(contest.starts_at) }}</dd>
        </div>
        <div>
          <dt>{{ $tr('Contest end') }}</dt>
          <dd>{{ formatUtc(contest.ends_at) }}</dd>
        </div>
        <div>
          <dt>{{ $tr('Log submission cutoff') }}</dt>
          <dd>{{ formatUtc(contest.log_submission_cutoff_at) }}</dd>
        </div>
      </dl>
      <p v-if="acceptsLogs()" class="contest-upload-action">
        <RouterLink
          class="primary-button"
          :to="{ path: '/submit-log', query: { contest: contest.slug } }"
        >
          {{ $tr('Submit a log for this contest') }}
        </RouterLink>
      </p>
      <p v-else-if="contest.status === 'open'" class="notice">
        {{ $tr('Log submissions are closed for this contest.') }}
      </p>
      <RouterLink
        v-if="contest.status === 'published'"
        class="results-link"
        :to="`/contests/${encodeURIComponent(contest.slug)}/results`"
      >
        {{ $tr('View published results') }} <span aria-hidden="true">→</span>
      </RouterLink>
    </template>
  </section>
</template>

<style scoped>
.public-contest {
  max-width: 52rem;
  margin: 2rem auto;
}
.contest-dates {
  display: grid;
  gap: 0.75rem;
}
.contest-description {
  margin: 0.75rem 0 1.5rem;
}
.markdown-content :deep(p:first-child) {
  margin-top: 0;
}
.markdown-content :deep(p:last-child),
.markdown-content :deep(ul:last-child),
.markdown-content :deep(ol:last-child) {
  margin-bottom: 0;
}
.ruleset-overview {
  margin: 1.5rem 0;
  padding: 1rem 1.25rem;
  border: 1px solid var(--border, #ded2c9);
  border-radius: 0.5rem;
  background: var(--surface, #fffdfa);
}
.ruleset-overview h2 {
  margin-top: 0;
  font-size: 1.2rem;
}
.generated-summary-note {
  color: var(--muted, #65564d);
  font-size: 0.95rem;
}
.ruleset-overview ul {
  margin-bottom: 0;
  padding-left: 1.25rem;
}
.ruleset-overview ul.summary-detail-list {
  margin-top: 0.45rem;
  padding-left: 1.5rem;
}
.ruleset-overview li > p {
  margin: 0.45rem 0 0;
}
.ruleset-overview li + li {
  margin-top: 0.45rem;
}
.cabrillo-example {
  margin-top: 1.25rem;
}
.cabrillo-example h3 {
  margin-bottom: 0.5rem;
  font-size: 1rem;
}
.cabrillo-example pre {
  overflow-x: auto;
  margin: 0;
  padding: 0.9rem;
  border-radius: 0.35rem;
  background: var(--code-surface, #f4eee9);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.875rem;
  line-height: 1.5;
  white-space: pre;
}
.contest-dates div {
  display: grid;
  grid-template-columns: minmax(10rem, 1fr) 2fr;
  gap: 1rem;
}
.contest-dates dt {
  font-weight: 700;
}
.contest-dates dd {
  margin: 0;
}
.contest-upload-action {
  margin-top: 1.5rem;
}
@media (max-width: 36rem) {
  .contest-dates div {
    grid-template-columns: 1fr;
    gap: 0.2rem;
  }
}
</style>
