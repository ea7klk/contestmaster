<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { ApiError } from '../api/client'
import { getPublicContest, type PublicContestDetails } from '../api/results'
import { describeContestRuleset } from './publicContestDescription'

const props = defineProps<{ slug: string }>()
const contest = ref<PublicContestDetails | null>(null)
const loading = ref(true)
const error = ref('')
const rulesetSummary = computed(() =>
  describeContestRuleset(contest.value?.ruleset ?? null),
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
      <p v-if="contest.description">{{ contest.description }}</p>
      <section
        class="ruleset-overview"
        aria-labelledby="ruleset-overview-title"
      >
        <h2 id="ruleset-overview-title">Contest rules at a glance</h2>
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
