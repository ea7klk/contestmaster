<template>
  <footer class="site-footer">
    <p class="project-credits">
      {{
        $tr(
          'Copyright © 2026 Volker Kerkhoff and contributors. Contestmaster is licensed under AGPL-3.0-only.',
        )
      }}
      <a
        href="https://github.com/ea7klk/contestmaster"
        target="_blank"
        rel="noreferrer"
        >{{ $tr('Project repository') }}</a
      >
      ·
      <a
        href="https://github.com/ea7klk/contestmaster/blob/main/LICENSE"
        target="_blank"
        rel="noreferrer"
        >{{ $tr('License') }}</a
      >
    </p>
    <p>
      {{ $tr('Callsign and entity reference data: Big CTY') }}
      <a
        href="https://www.country-files.com/cty/"
        target="_blank"
        rel="noreferrer"
        >{{ $tr('cty.dat') }}</a
      >
      (<a
        href="https://github.com/WSJTX/wsjtx/blob/master/cty.dat_copyright.txt"
        target="_blank"
        rel="noreferrer"
        >{{ $tr('license and use terms') }}</a
      >).
    </p>
  </footer>
</template>

<style scoped>
.site-footer {
  text-align: center;
}
</style>
