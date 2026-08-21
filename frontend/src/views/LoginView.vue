<template>
  <div class="page" style="max-width: 520px">
    <el-card>
      <template #header>
        <div>
          <h2 style="margin: 0">Redmine 固件版本发布工具 <span class="muted">v{{ version || '-' }}</span></h2>
          <div class="muted">Vue + FastAPI 开发版</div>
        </div>
      </template>

      <div class="native-auth-mode">
        <label><input v-model="form.auth_mode" type="radio" value="password" /> 用户名密码</label>
        <label><input v-model="form.auth_mode" type="radio" value="api_key" /> API Key</label>
      </div>

      <form v-if="form.auth_mode === 'password'" action="/login" accept-charset="UTF-8" method="post" class="native-login-form">
        <label for="username">登录名</label>
        <input id="username" v-model="form.username" type="text" name="username" tabindex="1" autofocus />

        <label for="password">密码</label>
        <input id="password" v-model="form.password" type="password" name="password" tabindex="2" />

        <label class="native-login-checkbox" for="remember">
          <input id="remember" v-model="form.remember" type="checkbox" name="remember" value="true" tabindex="4" />
          保持登录状态
        </label>

        <input id="login-submit" type="submit" name="login" value="登录" tabindex="5" />
      </form>

      <form v-else class="native-login-form" @submit.prevent="submitApiKey">
        <label for="api-key">API Key</label>
        <input id="api-key" v-model="form.api_key" type="password" autocomplete="off" />
        <label class="native-login-checkbox" for="api-remember">
          <input id="api-remember" v-model="form.remember" type="checkbox" />
          保持登录状态
        </label>
        <button type="submit" :disabled="loading">{{ loading ? '登录中…' : '登录' }}</button>
      </form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
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

async function submitApiKey() {
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

onMounted(() => {
  const url = new URL(window.location.href)
  const loginError = url.searchParams.get('login_error')
  if (!loginError) return
  ElMessage.error(loginError)
  url.searchParams.delete('login_error')
  window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
})
</script>

<style scoped>
.native-auth-mode {
  display: flex;
  gap: 20px;
  margin-bottom: 18px;
}

.native-auth-mode label,
.native-login-checkbox {
  display: flex;
  gap: 7px;
  align-items: center;
  cursor: pointer;
}

.native-login-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.native-login-form > label:not(.native-login-checkbox) {
  margin-top: 4px;
  font-weight: 600;
}

.native-login-form > input[type='text'],
.native-login-form > input[type='password'] {
  box-sizing: border-box;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #c0c4cc;
  border-radius: 4px;
  font: inherit;
}

.native-login-checkbox {
  margin: 10px 0;
}

.native-login-form > input[type='submit'],
.native-login-form > button[type='submit'] {
  width: 100%;
  padding: 10px 16px;
  border: 0;
  border-radius: 4px;
  background: #409eff;
  color: #fff;
  cursor: pointer;
  font: inherit;
}

.native-login-form > button:disabled {
  cursor: wait;
  opacity: 0.65;
}
</style>
