<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { ApiError } from '../api/client'
import { listPublicContests, type PublicContest } from '../api/results'

const contests = ref<PublicContest[]>([])
const loading = ref(true)
const error = ref('')

onMounted(async () => {
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
})
</script>

<template>
  <section aria-labelledby="welcome-title" class="welcome-card">
    <p class="eyebrow">Contest operations, made clear</p>
    <h1 id="welcome-title">Contestmaster results</h1>
    <p class="intro">
      Browse published amateur radio contest results. Contest standings are
      public; log contacts and organizer review notes remain private.
    </p>
  </section>

  <section class="published-contests" aria-labelledby="published-contests-title">
    <h2 id="published-contests-title">Published contests</h2>
    <p v-if="loading" role="status" class="notice">Loading published contests…</p>
    <p v-else-if="error" role="alert" class="error-panel">{{ error }}</p>
    <p v-else-if="contests.length === 0" class="notice">
      No contest results have been published yet.
    </p>
    <ul v-else class="contest-cards">
      <li v-for="contest in contests" :key="contest.id" class="panel">
        <p class="eyebrow">{{ new Date(contest.starts_at).toLocaleDateString() }}</p>
        <h3>{{ contest.name }}</h3>
        <p v-if="contest.description">{{ contest.description }}</p>
        <RouterLink :to="`/contests/${encodeURIComponent(contest.slug)}/results`">
          View published results
        </RouterLink>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.published-contests {
  margin-top: 2.5rem;
}
.contest-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr));
  gap: 1rem;
  padding: 0;
  list-style: none;
}
.panel {
  padding: 1.25rem;
  border: 1px solid #d4e0e5;
  border-radius: 0.8rem;
  background: white;
}
.panel h3 {
  margin: 0.35rem 0 0.75rem;
}
</style>
