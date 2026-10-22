<template>
  <footer v-if="$slidev.nav.currentPage > 1 && !$slidev.nav.currentSlideRoute.meta.slide.frontmatter.apiSection" class="deck-footer">
    <span>Zig 0.17.0 / Linux I/O</span>
    <span>{{ $slidev.nav.currentPage }} / {{ $slidev.nav.total }}</span>
  </footer>
</template>
<style>
.deck-footer { position: absolute; z-index: 10; bottom: 10px; left: 52px; right: 52px; display: flex; justify-content: space-between; color: #a4b2c4; font: 11px sans-serif; pointer-events: none; }
</style>
