<template>
  <div v-if="checkingSession" class="page" style="max-width: 520px">
    <el-card><el-skeleton :rows="3" animated /></el-card>
  </div>
  <LoginView v-else-if="!session" :version="meta.app_version" @logged-in="handleLoggedIn" />
  <div v-else class="workspace-shell">
    <header class="workspace-header">
      <div class="workspace-header-inner">
        <div class="workspace-brand">
          <div class="workspace-brand-mark" aria-hidden="true">RF</div>
          <div>
            <div class="workspace-brand-name">Redmine 固件版本发布工具</div>
            <div class="workspace-brand-version">Release Operations · v{{ meta.app_version || '-' }}</div>
          </div>
        </div>

        <div class="workspace-account">
          <div class="workspace-avatar" aria-hidden="true">{{ session.user_login.slice(0, 1).toUpperCase() }}</div>
          <div class="workspace-user-copy">
            <strong>{{ session.user_login }}</strong>
            <span>{{ session.is_admin ? '管理员' : '普通用户' }}</span>
          </div>
          <div class="workspace-header-actions">
            <el-button class="logout-action" @click="handleLogout">退出</el-button>
          </div>
        </div>
      </div>
    </header>

    <main class="workspace-main">
      <el-tabs v-model="activeTab" class="workspace-tabs">
        <el-tab-pane v-if="session.is_admin" label="结构管理" name="wiki">
          <WikiConfigView :projects="session.projects" />
        </el-tab-pane>
        <el-tab-pane v-if="session.is_admin" label="旧项目升级" name="legacy">
          <LegacyMigrationView :projects="session.projects" />
        </el-tab-pane>
        <el-tab-pane label="邮件设置" name="mail">
          <MailSettingsView :session="session" @changed="mailVersion++" />
        </el-tab-pane>
        <el-tab-pane label="版本发布" name="publish">
          <ReleasePublishView :projects="session.projects" :meta="meta" :mail-version="mailVersion" />
        </el-tab-pane>
        <el-tab-pane label="版本编辑" name="edit">
          <ReleaseEditView :projects="session.projects" :meta="meta" :mail-version="mailVersion" />
        </el-tab-pane>
        <el-tab-pane label="发布记录" name="history">
          <PublishHistoryView :projects="session.projects" />
        </el-tab-pane>
      </el-tabs>
    </main>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import LoginView from './views/LoginView.vue'
import { errorMessage, getMe, getMeta, logout } from './api/http'
import type { MetaInfo, SessionInfo } from './types'

const LegacyMigrationView = defineAsyncComponent(() => import('./views/LegacyMigrationView.vue'))
const MailSettingsView = defineAsyncComponent(() => import('./views/MailSettingsView.vue'))
const PublishHistoryView = defineAsyncComponent(() => import('./views/PublishHistoryView.vue'))
const ReleaseEditView = defineAsyncComponent(() => import('./views/ReleaseEditView.vue'))
const ReleasePublishView = defineAsyncComponent(() => import('./views/ReleasePublishView.vue'))
const WikiConfigView = defineAsyncComponent(() => import('./views/WikiConfigView.vue'))

const session = ref<SessionInfo | null>(null)
const checkingSession = ref(true)
const activeTab = ref('publish')
const mailVersion = ref(0)
const meta = ref<MetaInfo>({ app_version: '', product_lines: [], mail_scopes: [], today: '' })

function handleLoggedIn(info: SessionInfo) {
  session.value = info
}

async function handleLogout() {
  await logout()
  session.value = null
}

onMounted(async () => {
  try {
    meta.value = await getMeta()
    session.value = await getMe()
  } catch (error) {
    session.value = null
    if (errorMessage(error) !== '请先登录 Redmine') {
      ElMessage.warning(errorMessage(error))
    }
  } finally {
    checkingSession.value = false
  }
})
</script>
