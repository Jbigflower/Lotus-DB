# Lotus Design System 使用指南

面向 Lotus-DB（混合型风格：极简工具 + 智能媒体 + 创作空间）的前端样式系统，强调“避免过度设计”，以最小原子样式满足媒体中心（A）、极简工具（B）、创意画廊（C）三种视觉模式。

- 技术栈：Vue 3 + Vite（可配合 Tauri）
- 文件位置：`src/styles/`（tokens、theme、base、components、animations、utilities、index）
- 样式导入：在 `src/main.ts` 中一次性 `import './styles/index.css'`

---

## 1. 快速接入

- 在入口文件导入样式
  ```ts
  // src/main.ts
  import './styles/index.css'
  // 其他 Vue 挂载逻辑...
  ```
- 默认跟随系统深浅色；也可手动：
  ```ts
  document.documentElement.dataset.theme = 'dark' // 或 'light'
  ```
- 三种视觉模式（只影响圆角/阴影/间距与表面色）
  - 模式 A（媒体中心）：页面根元素加 `.mode-media`
  - 模式 B（极简工具）：页面根元素加 `.mode-tool`
  - 模式 C（创意画廊）：页面根元素加 `.mode-gallery`

建议：为不同页面路由的根容器设置对应模式类，三种模式与深浅色可独立切换。

---

## 2. 设计令牌与主题

- 令牌（`tokens.css`）包含字体、字号、间距、圆角、动效时长与缓动、基础布局宽度、z-index。
- 主题（`theme.css`）定义 Light/Dark 语义色与阴影，并提供 A/B/C 模式的强度调节变量。
- 品牌色：`--brand: #7c3aed`（Lotus Purple），交互强调色：`--accent: #22d3ee`。

修改品牌色：
```css
/* 在 theme.css 中替换品牌值或在页面根覆盖 */
:root { --brand: #8b5cf6; }
```

注意：`color-mix(in oklab, ...)` 用于柔和混色，现代浏览器支持良好；不支持时将回退为基础色。

---

## 3. 常用组件

所有组件为类选择器，可直接在模板中使用。

- 按钮（`.btn`）
  - 变体：`.btn--primary` `.btn--secondary` `.btn--ghost` `.btn--danger`
  - 尺寸：`.btn--sm` `.btn--lg`
  ```html
  <button class="btn btn--primary">保存</button>
  <button class="btn btn--secondary">取消</button>
  <button class="btn btn--ghost">更多</button>
  ```

- 输入类（`.input` `.select` `.textarea`）
  ```html
  <input class="input" placeholder="输入关键词" />
  <select class="select"><option>A</option></select>
  <textarea class="textarea" placeholder="备注"></textarea>
  ```

- 搜索输入组（`.input-group`）
  ```html
  <div class="input-group">
    <span class="icon">🔍</span>
    <input class="input" placeholder="搜索影片、标签、人物…" />
  </div>
  ```

- 过滤 Chip（`.chip` + `.chip--active`）
  ```html
  <button class="chip chip--active">电影</button>
  <button class="chip">电视剧</button>
  ```

- 卡片（`.card`）
  ```html
  <article class="card card--hover">
    <h3>Inception</h3>
    <p class="text-muted">2010 · Nolan</p>
  </article>
  ```

- Tabs（`.tabs`）
  ```html
  <nav class="tabs">
    <a class="tabs__item tabs__item--active">全部</a>
    <a class="tabs__item">已完成</a>
  </nav>
  ```

- Toolbar 与分段选择（`.toolbar` `.segmented`）
  ```html
  <div class="toolbar">
    <div class="segmented">
      <button class="segmented__item segmented__item--active">列表</button>
      <button class="segmented__item">网格</button>
    </div>
  </div>
  ```

- Tooltip（`.tooltip`，自行定位）
  ```html
  <div class="tooltip" style="top: 40px; left: 12px;">更多操作</div>
  ```

- 列表/网格（极简 B）
  ```html
  <section class="list">
    <article class="card">Item A</article>
    <article class="card">Item B</article>
  </section>

  <section class="grid">
    <article class="card">Card A</article>
    <article class="card">Card B</article>
  </section>
  ```

---

## 4. 动效与可访问性

- 入场：`anim-pop-in`、`anim-slide-up`、`anim-fade-in`
- 提示/遮罩：`anim-blur-in`、`anim-fade-in`
- 加载：`skeleton`（骨架），`anim-spin`（旋转）
- 可访问性：`prefers-reduced-motion` 自动禁用动画与平滑滚动

示例：
```html
<article class="card anim-pop-in">新内容</article>
<div class="skeleton" style="height:120px"></div>
```

---

## 5. 布局与工具类

- 布局：`.stack`（列）、`.cluster`（行）、`.wrap`（换行）、`.content`（居中容器）
- 文本：`.text-muted` `.text-secondary` `.text-brand` `.text-ellipsis`
- 背景：`.bg-surface` `.bg-surface-2` `.bg-brand`
- 阴影/圆角：`.shadow-1` `.shadow-2` / `.radius-sm|md|lg|pill`
- 隐藏可见性：`.sr-only`（屏幕阅读器友好）

示例：
```html
<section class="content stack">
  <header class="cluster wrap">
    <h1 class="text-brand">Lotus</h1>
    <span class="text-muted">智能媒体知识库</span>
  </header>
</section>
```

---

## 6. 页面示例：极简（B）检索页（列表/网格 + 拖拽 + 筛选）

```vue
<!-- 示例：views/RichSearchDemo.vue（演示用） -->
<template>
  <div class="mode-tool content stack">
    <header class="cluster wrap">
      <h1>检索</h1>
      <div class="segmented">
        <button class="segmented__item" :class="{ 'segmented__item--active': view==='list' }" @click="view='list'">列表</button>
        <button class="segmented__item" :class="{ 'segmented__item--active': view==='grid' }" @click="view='grid'">网格</button>
      </div>
    </header>

    <div class="toolbar cluster wrap">
      <div class="input-group" style="flex:1;">
        <span class="icon">🔍</span>
        <input class="input" v-model="q" placeholder="搜索影片、标签、人物…" />
      </div>
      <button class="btn btn--primary">搜索</button>
    </div>

    <div class="cluster wrap">
      <button class="chip" :class="{ 'chip--active': filters.type==='movie' }" @click="filters.type='movie'">电影</button>
      <button class="chip" :class="{ 'chip--active': filters.type==='tv' }" @click="filters.type='tv'">电视剧</button>
      <button class="chip" :class="{ 'chip--active': filters.type==='image' }" @click="filters.type='image'">图片</button>
    </div>

    <section :class="[view==='grid' ? 'grid' : 'list', 'anim-fade-in']">
      <article v-for="item in filtered" :key="item.id" class="card draggable"
               draggable="true"
               @dragstart="onDragStart(item)"
               @dragover.prevent
               @drop="onDrop(item)">
        <h3 class="text-ellipsis">{{ item.title }}</h3>
        <p class="text-muted">{{ item.meta }}</p>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
const view = ref<'list'|'grid'>('grid')
const q = ref('')
const filters = ref<{ type: 'movie'|'tv'|'image' } >({ type: 'movie' })

const items = ref([
  { id: 1, title: 'Inception', meta: '2010 · Nolan', type: 'movie' },
  { id: 2, title: 'Better Call Saul', meta: 'AMC', type: 'tv' },
  { id: 3, title: 'Lotus Poster', meta: 'Studio', type: 'image' },
])

const dragging = ref<number|null>(null)
function onDragStart(item: { id: number }) { dragging.value = item.id }
function onDrop(target: { id: number }) {
  if (dragging.value === null || dragging.value === target.id) return
  const from = items.value.findIndex(i => i.id === dragging.value)
  const to = items.value.findIndex(i => i.id === target.id)
  const moved = items.value.splice(from, 1)[0]
  items.value.splice(to, 0, moved)
  dragging.value = null
}

const filtered = computed(() =>
  items.value
    .filter(i => i.type === filters.value.type)
    .filter(i => i.title.toLowerCase().includes(q.value.toLowerCase()))
)
</script>
```

---

## 7. 主题与模式切换（可选 composable）

```ts
// 示例：src/composables/useTheme.ts（演示用）
export function useTheme() {
  const setTheme = (mode: 'light' | 'dark') => {
    document.documentElement.dataset.theme = mode
    localStorage.setItem('theme', mode)
  }
  const load = () => {
    const saved = localStorage.getItem('theme') as 'light' | 'dark' | null
    if (saved) document.documentElement.dataset.theme = saved
  }
  const setVisualMode = (el: HTMLElement, mode: 'media' | 'tool' | 'gallery') => {
    el.classList.remove('mode-media', 'mode-tool', 'mode-gallery')
    el.classList.add(`mode-${mode}`)
  }
  return { setTheme, load, setVisualMode }
}
```

在应用启动时：
```ts
// main.ts
import { useTheme } from './composables/useTheme'
const { load } = useTheme()
load()
```

---

## 8. 常见 FAQ

- 如何在同一应用同时使用三种视觉模式？  
  为不同页面根容器应用 `.mode-media` / `.mode-tool` / `.mode-gallery`，它们只影响强度型变量，不会破坏全局主题一致性。

- 阴影与圆角太强或太弱怎么办？  
  在页面根容器上覆盖：`--radius`、`--gap`、`--elev` 即可微调。

- 动效过多影响性能？  
  用户 `prefers-reduced-motion` 环境下会自动禁用；也可对特定元素移除 `anim-` 类。

---

## 9. 速查表（类名）

- 布局：`stack` `cluster` `wrap` `content`
- 文本：`text-muted` `text-secondary` `text-brand` `text-ellipsis`
- 背景：`bg-surface` `bg-surface-2` `bg-brand`
- 按钮：`btn` `btn--primary|secondary|ghost|danger` `btn--sm|lg`
- 输入：`input` `select` `textarea` `input-group`
- 卡片：`card` `card--hover`
- Chip：`chip` `chip--active`
- Tabs：`tabs` `tabs__item` `tabs__item--active`
- Toolbar：`toolbar` `segmented` `segmented__item` `segmented__item--active`
- 列表/网格：`list` `grid` `draggable` `dragging` `drop-placeholder`
- 动效：`anim-fade-in|fade-out|slide-up|slide-down|pop-in|blur-in|spin`，`skeleton`