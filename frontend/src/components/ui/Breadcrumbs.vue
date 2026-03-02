<script setup lang="ts">
/**
 * 使用方式：
 * - 传入 items（label/to）。
 *
 * 设计思路：
 * - 简洁导航面包屑：最小化 API；与 RouterLink 对接以进行路由跳转。
 *
 * 页面表现（PlainText）：
 * - 右侧以“/”分隔的面包屑列表；可点击的项使用 Link。
 */
import { RouterLink } from 'vue-router'

export interface Crumb {
  label: string
  to?: string
}

const props = defineProps<{
  items: Crumb[]
}>()
</script>

<template>
  <nav class="breadcrumbs">
    <ul>
      <li v-for="(c, i) in props.items" :key="i">
        <RouterLink v-if="c.to" :to="c.to">{{ c.label }}</RouterLink>
        <span v-else>{{ c.label }}</span>
        <span v-if="i < props.items.length - 1"> / </span>
      </li>
    </ul>
  </nav>
</template>