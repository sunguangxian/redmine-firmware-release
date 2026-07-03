<template>
  <LoginView v-if="!session" @logged-in="handleLoggedIn" />
  <div v-else class="page">
    <el-card class="card">
      <div class="toolbar">
        <div>
          <h2 style="margin: 0">Redmine 固件版本发布工具</h2>
          <div class="muted">当前用户：{{ session.user_login }} / {{ session.is_admin ? '管理员' : '普通用户' }}</div>
        </div>
        <div style="flex: 1"></div>
        <el-button @click="handleLogout">退出登录</el-button>
      </div>
    </el-card>

    <el-tabs v-model="activeTab" type="border-card">
      <el-tab-pane label="结构管理" name="wiki">
        <WikiConfigView :projects="session.projects" />
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
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import LoginView from './views/LoginView.vue'
import MailSettingsView from './views/MailSettingsView.vue'
import ReleaseEditView from './views/ReleaseEditView.vue'
import ReleasePublishView from './views/ReleasePublishView.vue'
import WikiConfigView from './views/WikiConfigView.vue'
import { errorMessage, getMe, getMeta, logout } from './api/http'
import type { MetaInfo, SessionInfo } from './types'

const session = ref<SessionInfo | null>(null)
const activeTab = ref('publish')
const mailVersion = ref(0)
const meta = ref<MetaInfo>({ product_lines: [], mail_scopes: [], today: '' })

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
  }
})
</script>
