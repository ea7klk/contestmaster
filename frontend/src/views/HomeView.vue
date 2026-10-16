<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { ApiError } from '../api/client'
import {
  listPublicContests,
  listUpcomingContests,
  type PublicContest,
} from '../api/results'

const contests = ref<PublicContest[]>([])
const upcomingContests = ref<PublicContest[]>([])
const loading = ref(true)
const upcomingLoading = ref(true)
const error = ref('')
const upcomingError = ref('')
const query = ref('')
const upcomingRange = ref<'week' | 'month' | 'three-months'>('month')
const serverAsOfMs = ref<number | null>(null)
const responseReceivedAtMs = ref<number | null>(null)
const clockNowMs = ref(Date.now())
let clockTimer: number | undefined
let refreshTimer: number | undefined
let upcomingRequestActive = false

const filteredContests = computed(() => {
  const normalizedQuery = query.value.trim().toLocaleLowerCase()
  if (!normalizedQuery) return contests.value
  return contests.value.filter((contest) =>
    [contest.name, contest.description ?? '', contest.slug]
      .join(' ')
      .toLocaleLowerCase()
      .includes(normalizedQuery),
  )
})

const estimatedServerNowMs = computed(() => {
  if (serverAsOfMs.value === null || responseReceivedAtMs.value === null)
    return clockNowMs.value
  return serverAsOfMs.value + (clockNowMs.value - responseReceivedAtMs.value)
})

function addUtcMonths(timestamp: number, months: number) {
  const date = new Date(timestamp)
  const dayOfMonth = date.getUTCDate()
  const targetMonth = date.getUTCMonth() + months
  const lastTargetDay = new Date(
    Date.UTC(date.getUTCFullYear(), targetMonth + 1, 0),
  ).getUTCDate()
  date.setUTCDate(1)
  date.setUTCMonth(targetMonth)
  date.setUTCDate(Math.min(dayOfMonth, lastTargetDay))
  return date.getTime()
}

const activeContests = computed(() =>
  upcomingContests.value.filter(
    (contest) =>
      Date.parse(contest.starts_at) <= estimatedServerNowMs.value &&
      Date.parse(contest.ends_at) > estimatedServerNowMs.value,
  ),
)

const upcomingRangeEndMs = computed(() => {
  const now = estimatedServerNowMs.value
  if (upcomingRange.value === 'week') return now + 7 * 24 * 60 * 60 * 1000
  return addUtcMonths(now, upcomingRange.value === 'month' ? 1 : 3)
})

const visibleUpcomingContests = computed(() =>
  upcomingContests.value.filter(
    (contest) =>
      Date.parse(contest.starts_at) > estimatedServerNowMs.value &&
      Date.parse(contest.starts_at) <= upcomingRangeEndMs.value,
  ),
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

async function loadPublishedContests() {
  try {
    contests.value = (await listPublicContests()).items
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'Published contests could not be loaded.'
  } finally {
    loading.value = false
  }
}

async function loadUpcomingContests() {
  if (upcomingRequestActive) return
  upcomingRequestActive = true
  try {
    const response = await listUpcomingContests()
    upcomingContests.value = response.items
    serverAsOfMs.value = Date.parse(response.as_of)
    responseReceivedAtMs.value = Date.now()
    upcomingError.value = ''
  } catch (cause) {
    upcomingError.value =
      cause instanceof ApiError
        ? cause.message
        : 'Upcoming contests could not be loaded.'
  } finally {
    upcomingLoading.value = false
    upcomingRequestActive = false
  }
}

onMounted(() => {
  void loadPublishedContests()
  void loadUpcomingContests()
  clockTimer = globalThis.setInterval(() => {
    clockNowMs.value = Date.now()
  }, 10_000)
  refreshTimer = globalThis.setInterval(() => {
    void loadUpcomingContests()
  }, 60_000)
})

onBeforeUnmount(() => {
  if (clockTimer !== undefined) globalThis.clearInterval(clockTimer)
  if (refreshTimer !== undefined) globalThis.clearInterval(refreshTimer)
})
</script>

<template>
  <div class="activity-home">
    <section class="activity-hero" aria-labelledby="welcome-title">
      <div class="activity-hero-copy">
        <p class="eyebrow">Public contest activity</p>
        <h1 id="welcome-title">Find a contest. Make your next contact.</h1>
        <p class="intro">
          Browse published amateur radio contest results, see when each contest
          ran, and upload a log without creating an account.
        </p>
        <RouterLink class="primary-button hero-upload" to="/submit-log">
          Submit a log <span aria-hidden="true">→</span>
        </RouterLink>
      </div>
      <div class="activity-hero-mark" aria-hidden="true">
        <span class="signal signal-one"></span>
        <span class="signal signal-two"></span>
        <span class="signal signal-three"></span>
        <span class="signal-center">73</span>
      </div>
    </section>

    <section class="active-contests" aria-labelledby="active-contests-title">
      <div class="feed-heading">
        <div>
          <p class="eyebrow">On the air now</p>
          <h2 id="active-contests-title">Active contests</h2>
          <p class="feed-description">
            Open contests currently in progress, shown in UTC.
          </p>
        </div>
      </div>
      <p v-if="upcomingLoading" role="status" class="notice feed-state">
        Loading active contests…
      </p>
      <p v-else-if="upcomingError" role="alert" class="error-panel feed-state">
        {{ upcomingError }}
      </p>
      <p v-else-if="activeContests.length === 0" class="notice feed-state">
        No contests are in progress right now.
      </p>
      <ul v-else class="contest-feed">
        <li v-for="contest in activeContests" :key="contest.id">
          <article class="contest-feed-card">
            <div class="contest-card-main">
              <div class="contest-card-title-row">
                <h3>{{ contest.name }}</h3>
                <span class="published-badge">In progress</span>
              </div>
              <p v-if="contest.description" class="contest-description">
                {{ contest.description }}
              </p>
              <dl class="contest-dates">
                <div>
                  <dt>Contest start</dt>
                  <dd>{{ formatUtc(contest.starts_at) }}</dd>
                </div>
                <div>
                  <dt>Contest end</dt>
                  <dd>{{ formatUtc(contest.ends_at) }}</dd>
                </div>
              </dl>
            </div>
            <RouterLink
              class="results-link"
              :to="`/contests/${encodeURIComponent(contest.slug)}`"
            >
              Contest details <span aria-hidden="true">→</span>
            </RouterLink>
          </article>
        </li>
      </ul>
    </section>

    <section
      class="upcoming-contests"
      aria-labelledby="upcoming-contests-title"
    >
      <div class="feed-heading">
        <div>
          <p class="eyebrow">Plan your next contest</p>
          <h2 id="upcoming-contests-title">Upcoming contests</h2>
          <p class="feed-description">
            Open contests starting within your selected date range, shown in
            UTC.
          </p>
        </div>
        <div class="upcoming-range-control">
          <label for="upcoming-range">Show contests for</label>
          <select id="upcoming-range" v-model="upcomingRange">
            <option value="week">Next week</option>
            <option value="month">Next month</option>
            <option value="three-months">Next 3 months</option>
          </select>
        </div>
      </div>
      <p v-if="upcomingLoading" role="status" class="notice feed-state">
        Loading upcoming contests…
      </p>
      <p v-else-if="upcomingError" role="alert" class="error-panel feed-state">
        {{ upcomingError }}
      </p>
      <p
        v-else-if="visibleUpcomingContests.length === 0"
        class="notice feed-state"
      >
        No contests are scheduled for the next
        {{
          upcomingRange === 'week'
            ? 'week'
            : upcomingRange === 'month'
              ? 'month'
              : '3 months'
        }}.
      </p>
      <ul v-else class="contest-feed">
        <li v-for="contest in visibleUpcomingContests" :key="contest.id">
          <article class="contest-feed-card">
            <div class="contest-card-main">
              <div class="contest-card-title-row">
                <h3>{{ contest.name }}</h3>
                <span class="published-badge">Upcoming</span>
              </div>
              <p v-if="contest.description" class="contest-description">
                {{ contest.description }}
              </p>
              <dl class="contest-dates">
                <div>
                  <dt>Contest start</dt>
                  <dd>{{ formatUtc(contest.starts_at) }}</dd>
                </div>
                <div>
                  <dt>Contest end</dt>
                  <dd>{{ formatUtc(contest.ends_at) }}</dd>
                </div>
              </dl>
            </div>
            <RouterLink
              class="results-link"
              :to="`/contests/${encodeURIComponent(contest.slug)}`"
            >
              Contest details <span aria-hidden="true">→</span>
            </RouterLink>
          </article>
        </li>
      </ul>
    </section>

    <section
      class="published-contests"
      aria-labelledby="published-contests-title"
    >
      <div class="feed-heading">
        <div>
          <p class="eyebrow">Explore the logbook</p>
          <h2 id="published-contests-title">Contest activity</h2>
          <p class="feed-description">
            Published contests and their final standings, in UTC.
          </p>
        </div>
        <form class="contest-search" role="search" @submit.prevent>
          <label for="contest-search">Find a published contest</label>
          <div class="contest-search-control">
            <input
              id="contest-search"
              v-model="query"
              type="search"
              placeholder="Search name or description"
              autocomplete="off"
            />
            <button
              v-if="query"
              type="button"
              class="quiet-button"
              @click="query = ''"
            >
              Clear
            </button>
          </div>
        </form>
      </div>

      <p v-if="loading" role="status" class="notice feed-state">
        Loading published contests…
      </p>
      <p v-else-if="error" role="alert" class="error-panel feed-state">
        {{ error }}
      </p>
      <p v-else-if="contests.length === 0" class="notice feed-state">
        No contest results have been published yet.
      </p>
      <template v-else>
        <p class="feed-count" aria-live="polite">
          Showing {{ filteredContests.length }} of
          {{ contests.length }} published
          {{ contests.length === 1 ? 'contest' : 'contests' }}.
        </p>
        <p v-if="filteredContests.length === 0" class="notice feed-state">
          No published contests match “{{ query }}”. Try another name or
          description.
        </p>
        <ul v-else class="contest-feed">
          <li v-for="contest in filteredContests" :key="contest.id">
            <article class="contest-feed-card">
              <div class="contest-card-main">
                <div class="contest-card-title-row">
                  <h3>{{ contest.name }}</h3>
                  <span class="published-badge">Results published</span>
                </div>
                <p v-if="contest.description" class="contest-description">
                  {{ contest.description }}
                </p>
                <dl class="contest-dates">
                  <div>
                    <dt>Contest start</dt>
                    <dd>{{ formatUtc(contest.starts_at) }}</dd>
                  </div>
                  <div>
                    <dt>Contest end</dt>
                    <dd>{{ formatUtc(contest.ends_at) }}</dd>
                  </div>
                </dl>
              </div>
              <RouterLink
                class="results-link"
                :to="`/contests/${encodeURIComponent(contest.slug)}/results`"
              >
                View published results <span aria-hidden="true">→</span>
              </RouterLink>
            </article>
          </li>
        </ul>
      </template>
    </section>
  </div>
</template>

<style scoped>
.activity-home {
  display: grid;
  gap: clamp(2rem, 5vw, 3.5rem);
}
.activity-hero {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2rem;
  overflow: hidden;
  min-height: 17rem;
  padding: clamp(1.5rem, 5vw, 3.25rem);
  border-radius: 0.9rem;
  color: var(--color-surface);
  background: var(--color-brand-700);
}
.activity-hero-copy {
  position: relative;
  z-index: 1;
  max-width: 48rem;
}
.activity-hero .eyebrow {
  color: var(--color-brand-soft);
}
.activity-hero h1 {
  max-width: 16ch;
  margin-top: 0.8rem;
  color: var(--color-surface);
  font-size: clamp(2rem, 4.5vw, 3.3rem);
}
.activity-hero .intro {
  max-width: 57ch;
  margin-bottom: 1.5rem;
  color: var(--color-brand-wash-strong);
}
.primary-button {
  min-height: 2.8rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.65rem;
  padding: 0.65rem 1rem;
  border: 1px solid var(--color-surface);
  border-radius: 0.45rem;
  color: var(--color-brand-900);
  background: var(--color-surface);
  font-weight: 750;
  text-decoration: none;
}
.primary-button:hover {
  color: var(--color-brand-900);
  background: var(--color-brand-wash-strong);
}
.activity-hero-mark {
  position: relative;
  width: 13rem;
  height: 13rem;
  flex: 0 0 13rem;
  display: grid;
  place-items: center;
  margin-right: 1rem;
  border: 1px solid var(--color-header-outline);
  border-radius: 50%;
  background: var(--color-brand-500);
  box-shadow:
    0 0 0 1.4rem var(--color-header-halo-one),
    0 0 0 2.8rem var(--color-header-halo-two);
}
.signal {
  position: absolute;
  border: 1px solid var(--color-header-circle);
  border-radius: 50%;
}
.signal-one {
  inset: 1.3rem;
}
.signal-two {
  inset: 2.7rem;
}
.signal-three {
  inset: 4.1rem;
}
.signal-center {
  display: grid;
  width: 4.2rem;
  height: 4.2rem;
  place-items: center;
  border-radius: 50%;
  color: var(--color-brand-900);
  background: var(--color-surface);
  font-size: 1.4rem;
  font-weight: 800;
}
.feed-heading {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 1.5rem;
  margin-bottom: 1.2rem;
}
.feed-heading h2 {
  margin: 0.25rem 0;
  font-size: clamp(1.55rem, 3vw, 2rem);
}
.feed-heading .eyebrow {
  margin: 0;
}
.feed-description {
  margin: 0;
  color: var(--color-muted);
}
.contest-search {
  width: min(100%, 25rem);
}
.contest-search label {
  display: block;
  margin-bottom: 0.4rem;
  color: var(--color-muted);
  font-size: 0.86rem;
  font-weight: 700;
}
.contest-search-control {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.contest-search input {
  width: 100%;
  min-height: 2.8rem;
  padding: 0.65rem 0.8rem;
  border: 1px solid var(--color-border-strong);
  border-radius: 0.45rem;
  color: var(--color-ink);
  background: var(--color-surface);
}
.upcoming-range-control {
  width: min(100%, 16rem);
}
.upcoming-range-control label {
  display: block;
  margin-bottom: 0.4rem;
  color: var(--color-muted);
  font-size: 0.86rem;
  font-weight: 700;
}
.upcoming-range-control select {
  width: 100%;
  min-height: 2.8rem;
  padding: 0.55rem 2rem 0.55rem 0.75rem;
  border: 1px solid var(--color-border-strong);
  border-radius: 0.45rem;
  color: var(--color-ink);
  background: var(--color-surface);
}
.quiet-button {
  min-height: 2.6rem;
  padding: 0.5rem 0.7rem;
  border: 0;
  color: var(--color-brand-700);
  background: transparent;
  font-weight: 700;
  cursor: pointer;
}
.feed-count {
  margin: 0 0 0.8rem;
  color: var(--color-muted);
  font-size: 0.9rem;
}
.contest-feed {
  display: grid;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.contest-feed-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.8rem 1rem;
  border: 1px solid var(--color-border);
  border-left: 5px solid var(--color-brand-600);
  border-radius: 0.7rem;
  background: var(--color-surface);
  box-shadow: 0 5px 16px var(--color-card-shadow);
}
.contest-card-main {
  min-width: 0;
  flex: 1;
}
.contest-card-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.contest-card-title-row h3 {
  margin: 0;
  font-size: 1.08rem;
}
.published-badge {
  display: inline-flex;
  min-height: 1.55rem;
  align-items: center;
  padding: 0.15rem 0.55rem;
  border: 1px solid var(--color-brand-line);
  border-radius: 999px;
  color: var(--color-brand-900);
  background: var(--color-brand-wash);
  font-size: 0.76rem;
  font-weight: 700;
}
.contest-description {
  margin: 0.3rem 0 0;
  color: var(--color-muted);
}
.contest-dates {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem 1.5rem;
  margin: 0.5rem 0 0;
}
.contest-dates div {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
.contest-dates dt {
  color: var(--color-muted);
  font-size: 0.82rem;
  font-weight: 650;
}
.contest-dates dd {
  margin: 0;
  color: var(--color-ink);
  font-size: 0.88rem;
  font-variant-numeric: tabular-nums;
}
.results-link {
  flex: 0 0 auto;
  padding: 0.5rem 0.65rem;
  border: 1px solid var(--color-border);
  border-radius: 0.45rem;
  color: var(--color-brand-700);
  font-size: 0.86rem;
  font-weight: 750;
  text-decoration: none;
}
.results-link:hover {
  border-color: var(--color-brand-600);
  color: var(--color-brand-900);
  background: var(--color-brand-wash);
}
.feed-state {
  padding: 1rem 1.2rem;
  border: 1px solid var(--color-border);
  border-radius: 0.6rem;
  background: var(--color-surface);
}
.error-panel {
  color: var(--color-error-ink);
  border-color: var(--color-error-border);
  background: var(--color-error-surface);
}
@media (max-width: 760px) {
  .activity-hero-mark {
    width: 9rem;
    height: 9rem;
    flex-basis: 9rem;
    margin-right: 0;
  }
  .signal-one {
    inset: 0.9rem;
  }
  .signal-two {
    inset: 1.8rem;
  }
  .signal-three {
    inset: 2.7rem;
  }
  .signal-center {
    width: 3rem;
    height: 3rem;
    font-size: 1rem;
  }
  .feed-heading {
    align-items: stretch;
    flex-direction: column;
  }
  .contest-search {
    width: 100%;
  }
  .upcoming-range-control {
    width: 100%;
  }
}
@media (max-width: 560px) {
  .activity-hero {
    min-height: 0;
    padding: 1.45rem;
  }
  .activity-hero-mark {
    display: none;
  }
  .contest-feed-card {
    align-items: stretch;
    flex-direction: column;
    gap: 0.65rem;
    padding: 0.75rem;
  }
  .contest-dates {
    display: grid;
    gap: 0.45rem;
  }
  .results-link {
    align-self: flex-start;
  }
}
</style>
