<script setup lang="ts">
import SiteFooter from './components/SiteFooter.vue'
</script>

<template>
  <div class="app-shell">
    <header class="site-header">
      <a class="wordmark" href="/" aria-label="Contestmaster home"
        >Contestmaster</a
      >
      <span class="header-caption">Amateur radio contest engine</span>
      <nav aria-label="Main navigation" class="site-navigation">
        <RouterLink to="/rulesets/compose">Ruleset composer</RouterLink>
      </nav>
    </header>
    <main id="main-content" class="main-content">
      <RouterView />
    </main>
    <SiteFooter />
  </div>
</template>
