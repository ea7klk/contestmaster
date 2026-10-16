<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { ApiError } from '../api/client'
import { getPublicContest, type PublicContestDetails } from '../api/results'
import { renderContestMarkdown } from './contestMarkdown'
import { describeContestRuleset } from './publicContestDescription'

const props = defineProps<{ slug: string }>()
const contest = ref<PublicContestDetails | null>(null)
const loading = ref(true)
const error = ref('')
const rulesetSummary = computed(() =>
  describeContestRuleset(contest.value?.ruleset ?? null),
)
const contestDescriptionHtml = computed(() =>
  renderContestMarkdown(contest.value?.description ?? null),
)

const utcDateTime = new Intl.DateTimeFormat('en-GB', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  timeZone: 'UTC',
})

function formatUtc(value: string) {
  return `${utcDateTime.format(new Date(value))} UTC`
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
    <p class="eyebrow">Public contest details</p>
    <p v-if="loading" role="status" class="notice">Loading contest details…</p>
    <p v-else-if="error" role="alert" class="error-panel">{{ error }}</p>
    <template v-else-if="contest">
      <h1 id="public-contest-title">{{ contest.name }}</h1>
      <!-- HTML is parsed and sanitized in contestMarkdown.ts before rendering. -->
      <!-- eslint-disable vue/no-v-html -->
      <section
        v-if="contestDescriptionHtml"
        class="contest-description markdown-content"
        aria-label="Contest description"
        v-html="contestDescriptionHtml"
      />
      <!-- eslint-enable vue/no-v-html -->
      <section
        class="ruleset-overview"
        aria-labelledby="ruleset-overview-title"
      >
        <h2 id="ruleset-overview-title">Contest rules at a glance</h2>
        <p class="generated-summary-note">
          This summary is automatically generated from the ruleset and may be
          imprecise. Refer to the contest’s official published rules for the
          authoritative requirements.
        </p>
        <ul v-if="rulesetSummary.length">
          <li v-for="(item, index) in rulesetSummary" :key="index">
            {{ item }}
          </li>
        </ul>
        <p v-else>Detailed contest rules are not available yet.</p>
      </section>
      <dl class="contest-dates">
        <div>
          <dt>Contest start</dt>
          <dd>{{ formatUtc(contest.starts_at) }}</dd>
        </div>
        <div>
          <dt>Contest end</dt>
          <dd>{{ formatUtc(contest.ends_at) }}</dd>
        </div>
        <div>
          <dt>Log submission cutoff</dt>
          <dd>{{ formatUtc(contest.log_submission_cutoff_at) }}</dd>
        </div>
      </dl>
      <p v-if="acceptsLogs()" class="contest-upload-action">
        <RouterLink
          class="primary-button"
          :to="{ path: '/submit-log', query: { contest: contest.slug } }"
        >
          Submit a log for this contest
        </RouterLink>
      </p>
      <p v-else-if="contest.status === 'open'" class="notice">
        Log submissions are closed for this contest.
      </p>
      <RouterLink
        v-if="contest.status === 'published'"
        class="results-link"
        :to="`/contests/${encodeURIComponent(contest.slug)}/results`"
      >
        View published results <span aria-hidden="true">→</span>
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
.ruleset-overview li + li {
  margin-top: 0.45rem;
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
