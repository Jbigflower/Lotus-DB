<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useUserStore } from '@/stores/user'
import { useUsersStore } from '@/stores/users'
import type { UserProfileDetails } from '@/types/user_settings'

const store = useUserStore()
const usersStore = useUsersStore()
const loading = ref(false)
const profile = ref<UserProfileDetails | null>(null)
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const displayName = computed(() => profile.value?.username ?? store.user?.username ?? '未登录')
const email = computed(() => profile.value?.email ?? store.user?.email ?? '-')
const role = computed(() => profile.value?.role ?? store.user?.role ?? '-')

async function fetchProfile() {
  if (!store.token) return
  loading.value = true
  try {
    // 直接使用当前登录用户信息展示基础资料
    const u = store.user
    profile.value = u
      ? {
          id: u.id,
          username: u.username,
          email: u.email,
          role: u.role,
          avatar_url: null,
        }
      : null
    await refreshAvatarSigned()
  } finally {
    loading.value = false
  }
}

async function refreshAvatarSigned() {
  if (!store.token || !store.user?.id) return
  try {
    const urls = await usersStore.getProfilesSigned(store.token, [store.user.id])
    const url = urls?.[0] ?? null
    if (profile.value && url) {
      profile.value.avatar_url = url
    }
  } catch {}
}

function pickFile() {
  if (!fileInput.value) return
  fileInput.value.click()
}

async function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || !store.token || !store.user?.id) return
  uploading.value = true
  try {
    const res = await usersStore.uploadProfile(store.token, store.user.id, file)
    if (res?.ok) {
      await fetchProfile()
      await refreshAvatarSigned()
    }
  } finally {
    uploading.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

onMounted(fetchProfile)
</script>

<template>
  <div class="content profile-view">
    <section class="card section">
      <div class="section-header">
        <h3 class="section-title">个人信息</h3>
        <div class="section-meta text-muted">查看并核对账户基础资料</div>
      </div>

      <div class="grid two">
        <div class="avatar-block card">
          <div class="avatar" :style="profile?.avatar_url ? { backgroundImage: `url(${profile?.avatar_url})` } : {}"></div>
          <div class="actions">
            <button class="btn" :disabled="uploading || !store.isAuthenticated" @click="pickFile">上传图像</button>
            <button class="btn secondary" :disabled="uploading || !store.isAuthenticated" @click="pickFile">更改图像</button>
            <input ref="fileInput" type="file" accept="image/*" class="hidden-file" @change="onFileSelected" />
          </div>
          <div v-if="uploading" class="hint text-muted">正在上传头像…</div>
        </div>
        <div class="info-block card">
          <div class="row"><span class="label">用户名称</span><span class="value">{{ displayName }}</span></div>
          <div class="row"><span class="label">用户邮箱</span><span class="value">{{ email }}</span></div>
          <div class="row"><span class="label">用户角色</span><span class="value">{{ role }}</span></div>
        </div>
      </div>
    </section>
  </div>
  
</template>

<style scoped>
.profile-view { padding-block: var(--space-5); }
.section { border-radius: var(--radius-lg); padding: var(--space-6); display: grid; gap: var(--space-5); box-shadow: var(--shadow-1); }
.section-header { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }
.section-title { font-size: var(--text-lg); font-weight: 600; margin: 0; }

.grid.two { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--gap); }
.card { padding: var(--space-5); border-radius: var(--radius-md); box-shadow: var(--shadow-0); background: var(--surface-1); }

.avatar { width: 120px; height: 120px; border-radius: var(--radius-round); background: color-mix(in oklab, var(--surface-2), black 5%); background-size: cover; background-position: center; }
.actions { display: flex; align-items: center; gap: var(--space-2); margin-top: var(--space-3); }
.btn { padding: 6px 10px; border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--surface-2); color: var(--text-secondary); cursor: pointer; }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.btn.secondary { background: var(--surface); }
.hidden-file { position: absolute; left: -10000px; width: 1px; height: 1px; opacity: 0; }
.row { display: flex; align-items: center; justify-content: space-between; padding: var(--space-2) 0; }
.label { color: var(--text-secondary); }
.value { color: var(--text-primary); font-weight: 600; }
.hint { margin-top: var(--space-2); }

@media (max-width: 768px) {
  .grid.two { grid-template-columns: 1fr; }
}
</style>