<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { ApiError } from '../api/client'
import { getPublicContest, type PublicContest } from '../api/results'

const props = defineProps<{ slug: string }>()
const contest = ref<PublicContest | null>(null)
const loading = ref(true)
const error = ref('')

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
