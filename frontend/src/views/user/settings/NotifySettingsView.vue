<script setup lang="ts">
// 暂留空占位视图
</script>

<template>
  <div class="content notify-settings-view">
    <section class="card section">
      <div class="section-header">
        <h3 class="section-title">通知设置</h3>
        <div class="section-meta text-muted">暂未实现，敬请期待</div>
      </div>
      <p class="hint text-muted">此模块仍在规划中，后续将支持站内通知、邮件与推送渠道的细粒度偏好设置。</p>
    </section>
  </div>
</template>

<style scoped>
.notify-settings-view { padding-block: var(--space-5); }
.section { border-radius: var(--radius-lg); padding: var(--space-6); display: grid; gap: var(--space-5); box-shadow: var(--shadow-1); }
.section-header { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }
.section-title { font-size: var(--text-lg); font-weight: 600; margin: 0; }
.hint { margin-top: var(--space-2); }
@media (max-width: 768px) { .section { padding: var(--space-5); } }
</style>