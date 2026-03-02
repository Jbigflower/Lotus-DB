<script setup lang="ts">
import { computed, ref, watch } from 'vue'

export interface FieldDef { key: string; label: string; width?: number | string }

const props = defineProps<{ allFields: FieldDef[]; activeKeys: string[]; compact?: boolean }>()
const emit = defineEmits<{ (e: 'update:activeKeys', v: string[]): void }>()

const localActive = ref<string[]>([...props.activeKeys])
const keySet = computed(() => new Set(localActive.value))
const inactive = computed(() => props.allFields.filter(f => !keySet.value.has(f.key)))

function add(key: string) {
  if (!keySet.value.has(key)) {
    const next = [...localActive.value, key]
    localActive.value = next
    emit('update:activeKeys', next)
  }
}
function remove(key: string) {
  const next = localActive.value.filter(k => k !== key)
  localActive.value = next
  emit('update:activeKeys', next)
}
function setActive(keys: string[]) { emit('update:activeKeys', keys) }

function onDragStart(e: DragEvent, key: string) {
  e.dataTransfer?.setData('text/plain', key)
}
function onDrop(e: DragEvent, targetKey: string) {
  const src = e.dataTransfer?.getData('text/plain')
  if (!src) return
  const arr = [...localActive.value]
  const from = arr.indexOf(src)
  const to = arr.indexOf(targetKey)
  if (from < 0 || to < 0) return
  arr.splice(from, 1)
  arr.splice(to, 0, src)
  setActive(arr)
}
function onDragOver(e: DragEvent) { e.preventDefault() }

watch(() => props.activeKeys, (v) => { localActive.value = [...v] })

const open = ref(false)

</script>

<template>
  <div class="field-manager">
    <template v-if="props.compact">
      <el-popover placement="bottom" :width="420" trigger="click" v-model:visible="open">
        <template #reference>
          <button class="icon-btn" aria-label="字段管理器">
            <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="6" height="16" rx="2"/><rect x="10" y="4" width="4" height="16" rx="2"/><rect x="15" y="4" width="6" height="16" rx="2"/></svg>
          </button>
        </template>
        <div class="panel">
          <div class="section">
            <div class="section-title">已激活字段</div>
            <div class="chips">
              <button
                v-for="key in localActive"
                :key="key"
                class="chip active"
                draggable="true"
                @dragstart="onDragStart($event, key)"
                @dragover="onDragOver"
                @drop="onDrop($event, key)"
                @click="remove(key)"
              >{{ props.allFields.find(f => f.key === key)?.label ?? key }}</button>
            </div>
          </div>
          <div class="section">
            <div class="section-title">未激活字段</div>
            <div class="chips">
              <button
                v-for="f in inactive"
                :key="f.key"
                class="chip"
                @click="add(f.key)"
              >{{ f.label }}</button>
            </div>
          </div>
        </div>
      </el-popover>
    </template>
    <template v-else>
      <details>
        <summary>字段管理器</summary>
        <div class="panel">
          <div class="section">
            <div class="section-title">已激活字段</div>
            <div class="chips">
              <button
                v-for="key in localActive"
                :key="key"
                class="chip active"
                draggable="true"
                @dragstart="onDragStart($event, key)"
                @dragover="onDragOver"
                @drop="onDrop($event, key)"
                @click="remove(key)"
              >{{ props.allFields.find(f => f.key === key)?.label ?? key }}</button>
            </div>
          </div>
          <div class="section">
            <div class="section-title">未激活字段</div>
            <div class="chips">
              <button
                v-for="f in inactive"
                :key="f.key"
                class="chip"
                @click="add(f.key)"
              >{{ f.label }}</button>
            </div>
          </div>
        </div>
      </details>
    </template>
  </div>
  </template>

<style scoped>
.field-manager { margin: 10px 0; }
details { border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); }
summary { cursor: pointer; padding: 10px 12px; font-weight: 600; }
.panel { display: grid; gap: 12px; padding: 12px; }
.section { display: grid; gap: 8px; }
.section-title { font-size: 12px; color: var(--text-secondary); }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { padding: 6px 10px; border-radius: 999px; border: 1px solid var(--border); background: var(--surface); cursor: pointer; }
.chip.active { background: color-mix(in oklab, var(--brand-weak), var(--surface) 60%); }
.icon-btn { width:34px; height:34px; display:inline-grid; place-items:center; border-radius: var(--radius); border:1px solid var(--border); background: var(--surface); color: var(--text-secondary); }
.icon-btn:hover { background: color-mix(in oklab, var(--surface), var(--brand-weak) 14%); color: var(--text-primary); }
.icon-btn svg { width:18px; height:18px; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
</style>
