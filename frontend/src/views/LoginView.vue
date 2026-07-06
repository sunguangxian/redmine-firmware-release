<template>
  <div class="page" style="max-width: 520px">
    <el-card>
      <template #header>
        <div>
          <h2 style="margin: 0">Redmine 固件版本发布工具 <span class="muted">v{{ version || '-' }}</span></h2>
          <div class="muted">Vue + FastAPI 开发版</div>
        </div>
      </template>

      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="登录方式">
          <el-radio-group v-model="form.auth_mode">
            <el-radio-button label="password">用户名密码</el-radio-button>
            <el-radio-button label="api_key">API Key</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <template v-if="form.auth_mode === 'password'">
          <el-form-item label="用户名">
            <el-input v-model="form.username" />
          </el-form-item>
          <el-form-item label="密码">
            <el-input v-model="form.password" type="password" show-password />
          </el-form-item>
        </template>

        <el-form-item v-else label="API Key">
          <el-input v-model="form.api_key" type="password" show-password />
        </el-form-item>

        <el-form-item>
          <el-checkbox v-model="form.remember">记住登录，下次打开自动恢复</el-checkbox>
        </el-form-item>

        <el-button type="primary" :loading="loading" style="width: 100%" @click="submit">登录</el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { errorMessage, login } from '../api/http'
import type { SessionInfo } from '../types'

defineProps<{ version: string }>()
const emit = defineEmits<{ 'logged-in': [value: SessionInfo] }>()
const loading = ref(false)
const form = reactive({
  auth_mode: 'password',
  username: '',
  password: '',
  api_key: '',
  remember: false
})

async function submit() {
  loading.value = true
  try {
    const data = await login(form)
    emit('logged-in', data)
    ElMessage.success(`已连接：${data.user_login}`)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    loading.value = false
  }
}
</script>
