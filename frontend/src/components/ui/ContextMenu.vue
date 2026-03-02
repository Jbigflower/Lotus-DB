<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'

export interface MenuItem {
  label: string
  icon?: string // SVG path or component
  action?: () => void
  disabled?: boolean
  divider?: boolean
  checked?: boolean // For toggle items
  shortcut?: string
}

const props = defineProps<{
  visible: boolean
  x: number
  y: number
  items: MenuItem[]
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'select', item: MenuItem): void
}>()

const menuRef = ref<HTMLElement | null>(null)

function close() {
  emit('update:visible', false)
}

function onClickOutside(e: MouseEvent) {
  if (props.visible && menuRef.value && !menuRef.value.contains(e.target as Node)) {
    close()
  }
}

function onItemClick(item: MenuItem) {
  if (item.disabled || item.divider) return
  if (item.action) item.action()
  emit('select', item)
  close()
}

// Close on ESC
function onKeydown(e: KeyboardEvent) {
  if (props.visible && e.key === 'Escape') {
    close()
  }
}

watch(() => props.visible, (val) => {
  if (val) {
    document.addEventListener('click', onClickOutside)
    document.addEventListener('keydown', onKeydown)
    // Prevent menu from going off-screen (simple adjustment)
    // We need to wait for next tick to get dimensions, but for now just rendering at x,y is fine
    // or we can use style binding
  } else {
    document.removeEventListener('click', onClickOutside)
    document.removeEventListener('keydown', onKeydown)
  }
})

onUnmounted(() => {
  document.removeEventListener('click', onClickOutside)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <teleport to="body">
    <transition name="fade">
      <div
        v-if="visible"
        ref="menuRef"
        class="context-menu"
        :style="{ top: `${y}px`, left: `${x}px` }"
        @contextmenu.prevent
      >
        <div
          v-for="(item, index) in items"
          :key="index"
          class="menu-item"
          :class="{ 'is-disabled': item.disabled, 'is-divider': item.divider }"
          @click.stop="onItemClick(item)"
        >
          <div v-if="item.divider" class="divider"></div>
          <template v-else>
            <span class="icon">
              <svg v-if="item.checked" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
              <svg v-else-if="item.icon" viewBox="0 0 24 24" aria-hidden="true"><path :d="item.icon"/></svg>
            </span>
            <span class="label">{{ item.label }}</span>
            <span v-if="item.shortcut" class="shortcut">{{ item.shortcut }}</span>
          </template>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<style scoped>
.context-menu {
  position: fixed;
  z-index: 9999;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
  padding: 4px 0;
  min-width: 180px;
  display: flex;
  flex-direction: column;
  color: var(--text-primary);
  font-size: 14px;
  user-select: none;
}

.menu-item {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  cursor: pointer;
  transition: background-color 0.2s;
  position: relative;
}

.menu-item:hover:not(.is-disabled):not(.is-divider) {
  background: var(--surface-variant, #f5f5f5);
}

.menu-item.is-disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.menu-item.is-divider {
  padding: 4px 0;
  cursor: default;
  height: 1px;
  margin: 4px 0;
  background-color: transparent;
}
.divider {
  height: 1px;
  background-color: var(--border);
  width: 100%;
}

.icon {
  width: 20px;
  height: 20px;
  margin-right: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
}

.icon svg {
  width: 16px;
  height: 16px;
  fill: currentColor;
}

.label {
  flex: 1;
}

.shortcut {
  margin-left: 12px;
  color: var(--text-tertiary, #999);
  font-size: 12px;
}

/* Dark mode adjustments if needed, usually variables handle it */
:global(.fade-enter-active),
:global(.fade-leave-active) {
  transition: opacity 0.15s ease;
}

:global(.fade-enter-from),
:global(.fade-leave-to) {
  opacity: 0;
}
</style>
