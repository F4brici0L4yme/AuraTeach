<script setup>
import { useSlideContext } from '@slidev/client'

const { $frontmatter } = useSlideContext()
</script>

<template>
  <div
    class="slidev-layout section-slide"
    :style="{ background: $frontmatter.background, color: $frontmatter.color }"
  >
    <div class="ghost-number" aria-hidden="true">{{ $frontmatter.number }}</div>
    <div class="section-inner">
      <div class="section-kicker">
        <span class="rule" />
        Sección {{ $frontmatter.number }}
      </div>
      <h1><slot /></h1>
      <p class="section-sub"><slot name="subtitle" /></p>
    </div>
    <div class="section-foot">IETF <span>·</span> RFC</div>
  </div>
</template>

<style scoped>
.section-slide {
  position: relative;
  height: 100%;
  width: 100%;
  display: flex;
  align-items: center;
  padding: 76px 92px !important;
  overflow: hidden;
}
.ghost-number {
  position: absolute;
  right: -18px;
  bottom: -168px;
  font-size: 470px;
  line-height: 0.8;
  font-weight: 900;
  letter-spacing: -0.08em;
  opacity: 0.12;
  pointer-events: none;
}
.section-inner {
  position: relative;
  z-index: 1;
  max-width: 850px;
}
.section-kicker {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  opacity: 0.72;
}
.rule {
  width: 44px;
  height: 3px;
  background: currentColor;
  opacity: 0.55;
}
h1 {
  margin: 26px 0 0;
  font-size: 88px;
  line-height: 0.96;
  font-weight: 900;
  letter-spacing: -0.03em;
}
h1 :deep(p) {
  margin: 0 !important;
  font-size: inherit !important;
  line-height: inherit !important;
  letter-spacing: inherit !important;
}
.section-sub {
  margin: 26px 0 0;
  font-size: 23px;
  font-weight: 700;
  letter-spacing: 0.02em;
  opacity: 0.8;
}
.section-sub :deep(p) {
  margin: 0 !important;
  font-size: inherit !important;
  line-height: 1.35 !important;
}
.section-foot {
  position: absolute;
  right: 92px;
  bottom: 54px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  opacity: 0.5;
}
.section-foot span {
  margin: 0 6px;
}
</style>
