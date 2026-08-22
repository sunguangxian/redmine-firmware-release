<template>
  <div class="login-page">
    <div class="login-orb login-orb-one"></div>
    <div class="login-orb login-orb-two"></div>

    <main class="login-card">
      <section class="login-brand" aria-label="产品介绍">
        <div>
          <div class="brand-mark" aria-hidden="true">
            <span>RF</span>
          </div>
          <p class="brand-eyebrow">RELEASE OPERATIONS</p>
          <h1>让每一次固件发布<br />清晰、可靠、可追溯</h1>
          <p class="brand-summary">
            连接 Redmine，集中完成版本维护、Release Wiki 同步、固件附件和邮件通知。
          </p>
        </div>

        <div class="brand-capabilities" aria-label="主要能力">
          <div class="capability-item"><span aria-hidden="true">01</span>统一版本发布流程</div>
          <div class="capability-item"><span aria-hidden="true">02</span>自动同步 Wiki 与索引</div>
          <div class="capability-item"><span aria-hidden="true">03</span>完整操作记录与恢复</div>
        </div>

        <div class="brand-version">Redmine Firmware Release · v{{ version || '-' }}</div>
      </section>

      <section class="login-auth" aria-labelledby="login-title">
        <header class="login-heading">
          <p class="login-kicker">欢迎回来</p>
          <h2 id="login-title">登录发布工作台</h2>
          <p>使用你的 Redmine 凭据继续，账号密码仅交由浏览器管理。</p>
        </header>

        <div class="native-auth-mode" role="radiogroup" aria-label="登录方式">
          <label>
            <input v-model="form.auth_mode" type="radio" value="password" />
            <span>用户名密码</span>
          </label>
          <label>
            <input v-model="form.auth_mode" type="radio" value="api_key" />
            <span>API Key</span>
          </label>
        </div>

        <form
          v-if="form.auth_mode === 'password'"
          id="login-form"
          name="login"
          action="/login"
          accept-charset="UTF-8"
          method="post"
          autocomplete="on"
          class="native-login-form"
          @submit="submitPassword"
        >
          <label for="login-username">登录名</label>
          <input
            id="login-username"
            v-model="form.username"
            type="text"
            name="username"
            autocomplete="username"
            placeholder="请输入 Redmine 登录名"
            tabindex="1"
            autofocus
            required
          />

          <label for="current-password">密码</label>
          <input
            id="current-password"
            v-model="form.password"
            type="password"
            name="password"
            autocomplete="current-password"
            placeholder="请输入登录密码"
            tabindex="2"
            required
          />

          <div class="login-options">
            <label class="native-login-checkbox" for="remember">
              <input id="remember" v-model="form.remember" type="checkbox" name="remember" value="true" tabindex="4" />
              <span>保持登录状态</span>
            </label>
            <span class="option-hint">由浏览器安全保存凭据</span>
          </div>

          <button id="login-submit" type="submit" tabindex="5" :disabled="loading">
            <span>{{ loading ? '正在连接 Redmine…' : '进入工作台' }}</span>
            <span class="submit-arrow" aria-hidden="true">→</span>
          </button>
        </form>

        <form v-else class="native-login-form" @submit.prevent="submitApiKey">
          <label for="api-key">API Key</label>
          <input
            id="api-key"
            v-model="form.api_key"
            type="password"
            autocomplete="off"
            placeholder="请输入 Redmine API Key"
            required
          />
          <div class="login-options">
            <label class="native-login-checkbox" for="api-remember">
              <input id="api-remember" v-model="form.remember" type="checkbox" />
              <span>保持登录状态</span>
            </label>
          </div>
          <button type="submit" :disabled="loading">
            <span>{{ loading ? '正在连接 Redmine…' : '进入工作台' }}</span>
            <span class="submit-arrow" aria-hidden="true">→</span>
          </button>
        </form>

        <footer class="login-footer">
          <span class="security-dot" aria-hidden="true"></span>
          凭据只用于连接当前配置的 Redmine，不会写入本地配置文件
        </footer>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, reactive, ref } from 'vue'
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

type PasswordCredentialConstructor = new (form: HTMLFormElement) => Credential

function browserPasswordCredentialConstructor(): PasswordCredentialConstructor | undefined {
  return (window as typeof window & { PasswordCredential?: PasswordCredentialConstructor }).PasswordCredential
}

async function submitPassword(event: SubmitEvent) {
  const nativeForm = event.currentTarget as HTMLFormElement
  const PasswordCredential = browserPasswordCredentialConstructor()

  // Credential Management API 只能在安全上下文中使用。HTTPS/localhost 下显式交给浏览器
  // 保存；普通 HTTP 内网地址则不拦截，让原生 POST 导航触发浏览器自身的密码管理器。
  if (!window.isSecureContext || !PasswordCredential || !navigator.credentials?.store) {
    loading.value = true
    return
  }

  event.preventDefault()
  loading.value = true
  try {
    const data = await login(form)
    try {
      await navigator.credentials.store(new PasswordCredential(nativeForm))
    } catch (error) {
      // 用户拒绝保存或浏览器策略禁用密码保存时，不影响已经成功的登录；
      // 同时保留诊断信息，避免保存失败被完全静默吞掉。
      console.warn('浏览器未能通过 Credential API 保存登录凭据', error)
    }
    emit('logged-in', data)
    // Chromium 把“登录表单消失 + 导航（含同文档导航）”作为成功登录信号。
    // Vue 更新 DOM 后产生一次不改变地址的 history 记录，触发密码管理器的
    // SPA 登录检测；这也是 Credential API 被策略拒绝时的回退路径。
    await nextTick()
    window.history.pushState({ authenticated: true }, '', window.location.href)
    ElMessage.success(`已连接：${data.user_login}`)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    loading.value = false
  }
}

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
.login-page {
  position: relative;
  display: grid;
  min-height: 100vh;
  box-sizing: border-box;
  place-items: center;
  overflow: hidden;
  padding: 40px 24px;
  background:
    linear-gradient(135deg, rgba(238, 244, 255, 0.96), rgba(247, 250, 255, 0.98) 48%, rgba(238, 249, 247, 0.96)),
    #f4f7fb;
}

.login-page::before {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(65, 88, 118, 0.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(65, 88, 118, 0.045) 1px, transparent 1px);
  background-size: 40px 40px;
  content: '';
  mask-image: linear-gradient(to bottom, black, transparent 78%);
}

.login-orb {
  position: absolute;
  border-radius: 999px;
  filter: blur(2px);
  pointer-events: none;
}

.login-orb-one {
  top: -180px;
  right: -100px;
  width: 440px;
  height: 440px;
  background: rgba(47, 111, 237, 0.1);
}

.login-orb-two {
  bottom: -220px;
  left: -130px;
  width: 480px;
  height: 480px;
  background: rgba(31, 168, 145, 0.09);
}

.login-card {
  position: relative;
  z-index: 1;
  display: grid;
  width: min(100%, 980px);
  min-height: 620px;
  grid-template-columns: minmax(0, 1.02fr) minmax(420px, 0.98fr);
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.82);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 30px 80px rgba(38, 58, 86, 0.16), 0 4px 14px rgba(38, 58, 86, 0.06);
  backdrop-filter: blur(16px);
}

.login-brand {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  overflow: hidden;
  padding: 52px 50px 42px;
  background: linear-gradient(145deg, #173a72 0%, #225aa5 58%, #1b7990 120%);
  color: #fff;
}

.login-brand::before,
.login-brand::after {
  position: absolute;
  border: 1px solid rgba(255, 255, 255, 0.11);
  border-radius: 999px;
  content: '';
}

.login-brand::before {
  right: -190px;
  bottom: -145px;
  width: 420px;
  height: 420px;
}

.login-brand::after {
  right: -105px;
  bottom: -60px;
  width: 250px;
  height: 250px;
  background: rgba(255, 255, 255, 0.035);
}

.brand-mark {
  display: grid;
  width: 48px;
  height: 48px;
  margin-bottom: 44px;
  place-items: center;
  border: 1px solid rgba(255, 255, 255, 0.32);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.12);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.2);
  font-size: 15px;
  font-weight: 800;
  letter-spacing: 0.06em;
}

.brand-eyebrow,
.login-kicker {
  margin: 0 0 12px;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.18em;
}

.brand-eyebrow {
  color: #9edaf0;
}

.login-brand h1 {
  margin: 0;
  font-size: clamp(30px, 3.3vw, 42px);
  line-height: 1.28;
  letter-spacing: -0.04em;
}

.brand-summary {
  max-width: 390px;
  margin: 22px 0 0;
  color: rgba(230, 242, 255, 0.78);
  font-size: 14px;
  line-height: 1.9;
}

.brand-capabilities {
  display: grid;
  gap: 12px;
  margin-top: 42px;
}

.capability-item {
  display: flex;
  gap: 12px;
  align-items: center;
  color: rgba(240, 247, 255, 0.9);
  font-size: 13px;
}

.capability-item span {
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.11);
  color: #aee7f2;
  font-size: 10px;
  font-weight: 800;
}

.brand-version {
  position: relative;
  z-index: 1;
  margin-top: 36px;
  color: rgba(220, 237, 255, 0.54);
  font-size: 11px;
  letter-spacing: 0.04em;
}

.login-auth {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 52px 54px 42px;
}

.login-heading {
  margin-bottom: 28px;
}

.login-kicker {
  color: #2f6fed;
}

.login-heading h2 {
  margin: 0;
  color: #17243a;
  font-size: 28px;
  line-height: 1.3;
  letter-spacing: -0.03em;
}

.login-heading > p:last-child {
  margin: 10px 0 0;
  color: #748196;
  font-size: 13px;
  line-height: 1.7;
}

.native-auth-mode {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  margin-bottom: 28px;
  padding: 4px;
  border: 1px solid #e3e9f2;
  border-radius: 12px;
  background: #f3f6fa;
}

.native-auth-mode label {
  position: relative;
  cursor: pointer;
}

.native-auth-mode input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
}

.native-auth-mode span {
  display: block;
  padding: 9px 12px;
  border-radius: 8px;
  color: #718096;
  font-size: 13px;
  font-weight: 600;
  text-align: center;
  transition: 160ms ease;
}

.native-auth-mode input:checked + span {
  background: #fff;
  box-shadow: 0 2px 8px rgba(43, 61, 86, 0.09);
  color: #245fbf;
}

.native-auth-mode input:focus-visible + span {
  outline: 2px solid rgba(47, 111, 237, 0.42);
  outline-offset: 2px;
}

.native-login-form {
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.native-login-form > label:not(.native-login-checkbox) {
  margin-top: 7px;
  color: #344054;
  font-size: 13px;
  font-weight: 650;
}

.native-login-form > input[type='text'],
.native-login-form > input[type='password'] {
  box-sizing: border-box;
  width: 100%;
  height: 48px;
  padding: 0 15px;
  border: 1px solid #d8e0eb;
  border-radius: 11px;
  outline: none;
  background: #fbfcfe;
  color: #1c293c;
  font: inherit;
  font-size: 14px;
  transition: border-color 160ms ease, box-shadow 160ms ease, background 160ms ease;
}

.native-login-form > input::placeholder {
  color: #a7b0bf;
}

.native-login-form > input:hover {
  border-color: #b8c5d6;
}

.native-login-form > input:focus {
  border-color: #4a7fe5;
  background: #fff;
  box-shadow: 0 0 0 4px rgba(47, 111, 237, 0.1);
}

.login-options {
  display: flex;
  min-height: 38px;
  justify-content: space-between;
  align-items: center;
  margin: 8px 0 5px;
}

.native-login-checkbox {
  display: flex;
  gap: 8px;
  align-items: center;
  color: #536176;
  cursor: pointer;
  font-size: 13px;
}

.native-login-checkbox input {
  width: 16px;
  height: 16px;
  margin: 0;
  accent-color: #2f6fed;
}

.option-hint {
  color: #98a2b3;
  font-size: 11px;
}

.native-login-form > button[type='submit'] {
  display: flex;
  width: 100%;
  height: 49px;
  justify-content: center;
  align-items: center;
  gap: 10px;
  margin-top: 2px;
  padding: 0 18px;
  border: 0;
  border-radius: 11px;
  background: linear-gradient(135deg, #2f6fed, #245bbd);
  box-shadow: 0 10px 20px rgba(47, 111, 237, 0.2);
  color: #fff;
  cursor: pointer;
  font: inherit;
  font-size: 14px;
  font-weight: 700;
  transition: transform 160ms ease, box-shadow 160ms ease, opacity 160ms ease;
}

.native-login-form > button[type='submit']:hover:not(:disabled) {
  box-shadow: 0 13px 24px rgba(47, 111, 237, 0.28);
  transform: translateY(-1px);
}

.native-login-form > button[type='submit']:active:not(:disabled) {
  box-shadow: 0 7px 14px rgba(47, 111, 237, 0.2);
  transform: translateY(0);
}

.native-login-form > button[type='submit']:focus-visible {
  outline: 3px solid rgba(47, 111, 237, 0.25);
  outline-offset: 3px;
}

.submit-arrow {
  font-size: 18px;
  font-weight: 400;
  line-height: 1;
}

.native-login-form > button:disabled {
  cursor: wait;
  opacity: 0.68;
}

.login-footer {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid #edf0f5;
  color: #8b96a8;
  font-size: 11px;
  line-height: 1.6;
}

.security-dot {
  flex: 0 0 auto;
  width: 7px;
  height: 7px;
  margin-top: 5px;
  border-radius: 50%;
  background: #22a06b;
  box-shadow: 0 0 0 4px rgba(34, 160, 107, 0.1);
}

@media (max-width: 820px) {
  .login-page {
    align-items: start;
    overflow: auto;
    padding: 22px 16px;
  }

  .login-card {
    min-height: auto;
    grid-template-columns: 1fr;
    border-radius: 22px;
  }

  .login-brand {
    min-height: auto;
    padding: 34px 32px;
  }

  .brand-mark {
    margin-bottom: 26px;
  }

  .brand-summary {
    margin-top: 14px;
  }

  .brand-capabilities {
    display: none;
  }

  .brand-version {
    margin-top: 22px;
  }

  .login-auth {
    padding: 38px 32px 32px;
  }
}

@media (max-width: 480px) {
  .login-page {
    padding: 0;
    background: #fff;
  }

  .login-page::before,
  .login-orb {
    display: none;
  }

  .login-card {
    width: 100%;
    border: 0;
    border-radius: 0;
    box-shadow: none;
  }

  .login-brand {
    padding: 28px 24px;
  }

  .login-brand h1 {
    font-size: 27px;
  }

  .brand-summary {
    font-size: 13px;
    line-height: 1.7;
  }

  .login-auth {
    padding: 32px 24px 28px;
  }

  .login-heading h2 {
    font-size: 25px;
  }

  .option-hint {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .native-auth-mode span,
  .native-login-form > input,
  .native-login-form > button[type='submit'] {
    transition: none;
  }
}
</style>
