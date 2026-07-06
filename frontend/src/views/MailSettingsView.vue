<template>
  <div>
    <el-alert class="card" type="info" :closable="false" show-icon>
      <template #title>邮件服务器由管理员配置；每个用户维护自己的内网账号、外网账号和外网联系人。外网联系人按当前外网 SMTP 用户名单独保存。</template>
    </el-alert>

    <el-card v-if="settings?.is_admin" class="card">
      <template #header>管理员配置</template>
      <div class="form-grid">
        <el-divider class="full-row" content-position="left">内网 SMTP</el-divider>
        <el-input v-model="settings.admin.internal_server.smtp_host" placeholder="内网 SMTP 服务器"><template #prepend>服务器</template></el-input>
        <el-input-number v-model="settings.admin.internal_server.smtp_port" :min="1" :max="65535" style="width: 100%" />
        <el-input v-model="settings.admin.internal_server.smtp_from" class="full-row" placeholder="firmware@company.local"><template #prepend>默认发件人</template></el-input>
        <el-checkbox v-model="settings.admin.internal_server.use_tls" class="full-row">内网使用 STARTTLS；465 端口自动 SSL</el-checkbox>

        <el-divider class="full-row" content-position="left">外网 SMTP 服务器</el-divider>
        <el-input v-model="settings.admin.external_server.smtp_host" placeholder="smtp.example.com"><template #prepend>服务器</template></el-input>
        <el-input-number v-model="settings.admin.external_server.smtp_port" :min="1" :max="65535" style="width: 100%" />
        <el-checkbox v-model="settings.admin.external_server.use_tls" class="full-row">外网使用 STARTTLS；465 端口自动 SSL</el-checkbox>

        <el-divider class="full-row" content-position="left">内网联系人</el-divider>
        <el-input v-model="internalContactText" class="full-row" type="textarea" :rows="5" placeholder="内网联系人，每行或逗号分隔一个邮箱" />
      </div>
      <div class="toolbar" style="margin-top: 16px">
        <el-button :loading="testingAdminInternal" @click="testAdminInternal">测试内网服务器</el-button>
        <el-button :loading="testingAdminExternal" @click="testAdminExternal">测试外网服务器</el-button>
        <el-button type="primary" :loading="savingAdmin" @click="saveAdmin">保存管理员邮件配置</el-button>
      </div>
    </el-card>

    <el-card class="card">
      <template #header>个人内网邮件账号</template>
      <div v-if="settings" class="form-grid">
        <el-input v-model="settings.user_internal.smtp_user" placeholder="内网 SMTP 用户名"><template #prepend>SMTP 用户名</template></el-input>
        <el-input v-model="settings.user_internal.smtp_password" type="password" show-password placeholder="不填写则保留旧密码">
          <template #prepend>SMTP 密码</template><template #append>{{ settings.user_internal.smtp_password_set ? '已设置' : '未设置' }}</template>
        </el-input>
        <el-input v-model="settings.user_internal.smtp_from" class="full-row" placeholder="user@company.local"><template #prepend>内网发件人</template></el-input>
      </div>
      <div class="toolbar" style="margin-top: 16px">
        <el-button :loading="testingInternal" @click="testInternal">测试内网账号</el-button>
        <el-button type="primary" :loading="savingInternal" @click="saveInternal">保存个人内网账号</el-button>
      </div>
    </el-card>

    <el-card class="card">
      <template #header>个人外网邮件账号和联系人</template>
      <div v-if="settings" class="form-grid">
        <el-input v-model="settings.user_external.smtp_user" placeholder="user@example.com" @change="handleExternalSmtpUserChange"><template #prepend>SMTP 用户名</template></el-input>
        <el-input v-model="settings.user_external.smtp_password" type="password" show-password placeholder="不填写则保留旧密码">
          <template #prepend>SMTP 密码</template><template #append>{{ settings.user_external.smtp_password_set ? '已设置' : '未设置' }}</template>
        </el-input>
        <el-input v-model="settings.user_external.smtp_from" class="full-row" placeholder="user@example.com"><template #prepend>外网发件人</template></el-input>

        <el-divider class="full-row" content-position="left">外网联系人</el-divider>
        <div class="full-row contact-template-list">
          <div v-for="(item, index) in externalPeople" :key="index" class="contact-row">
            <el-input v-model="item.name" placeholder="姓名" />
            <el-input v-model="item.email" placeholder="邮箱" />
            <el-button @click="externalPeople.splice(index, 1)">删除</el-button>
          </div>
          <el-button @click="addExternalPerson">新增外网联系人</el-button>
        </div>

        <el-divider class="full-row" content-position="left">外网联系人模板（可选）</el-divider>
        <div class="full-row contact-template-list">
          <div v-for="(item, index) in externalTemplates" :key="index" class="contact-template-item">
            <el-input v-model="item.name" placeholder="模块名，例如：客户A / 代理商 / 测试"><template #prepend>模块</template></el-input>
            <el-select v-model="item.emails" multiple filterable placeholder="选择联系人">
              <el-option v-for="option in externalContactOptions" :key="option.email" :label="option.label" :value="option.email" />
            </el-select>
            <el-button @click="externalTemplates.splice(index, 1)">删除模板</el-button>
          </div>
          <el-button @click="externalTemplates.push({ name: '', emails: [] })">新增外网联系人模板</el-button>
        </div>
      </div>
      <div class="toolbar" style="margin-top: 16px">
        <el-button :loading="testingUser" @click="testUser">测试外网账号</el-button>
        <el-button :loading="loadingExternalContacts" @click="loadExternalAccountContacts()">读取当前外网账号联系人</el-button>
        <el-button type="primary" :loading="savingUser" @click="saveUser">保存个人外网设置</el-button>
        <el-button :loading="loading" @click="load">重新读取</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { errorMessage, getExternalAccountContacts, getMailSettings, saveAdminMailSettings, saveUserExternalMailSettings, saveUserInternalMailSettings, testAdminMailServer, testMailConnection } from '../api/http'
import type { ContactPersonConfig, ContactTemplateConfig, MailSettings, SessionInfo } from '../types'

const props = defineProps<{ session: SessionInfo }>()
const emit = defineEmits<{ changed: [] }>()
const settings = ref<MailSettings | null>(null)
const loading = ref(false)
const savingAdmin = ref(false)
const savingInternal = ref(false)
const savingUser = ref(false)
const testingAdminInternal = ref(false)
const testingAdminExternal = ref(false)
const testingInternal = ref(false)
const testingUser = ref(false)
const loadingExternalContacts = ref(false)
const internalContactText = ref('')
const externalPeople = ref<ContactPersonConfig[]>([])
const externalTemplates = ref<Array<{ name: string; emails: string[] }>>([])

type MailScope = 'internal' | 'external'

function splitText(text: string): string[] { return text.split(/[\n,;，；\s]+/).map((item) => item.trim()).filter((item) => item.includes('@')) }
function nameFromEmail(email: string): string { return email.split('@')[0] || email }
function cleanPeople(items: ContactPersonConfig[]): ContactPersonConfig[] {
  const seen = new Set<string>()
  const result: ContactPersonConfig[] = []
  items.forEach((item) => {
    const email = item.email.trim()
    const key = email.toLowerCase()
    if (!email.includes('@') || seen.has(key)) return
    seen.add(key)
    result.push({ name: item.name.trim() || nameFromEmail(email), email })
  })
  return result
}
function emailToPerson(email: string): ContactPersonConfig { return externalPeople.value.find((item) => item.email.trim().toLowerCase() === email.trim().toLowerCase()) || { name: nameFromEmail(email), email } }
function editableExternalTemplates(items: ContactTemplateConfig[]) { return (items || []).map((item) => ({ name: item.name, emails: item.contacts_to.map((contact) => contact.email) })) }
function saveableExternalTemplates(): ContactTemplateConfig[] { return externalTemplates.value.map((item) => ({ name: item.name.trim(), contacts_to: item.emails.map(emailToPerson), contacts_cc: [] })).filter((item) => item.name) }
function addExternalPerson() { externalPeople.value.push({ name: '', email: '' }) }

const externalContactOptions = computed(() => cleanPeople(externalPeople.value).map((item) => ({ ...item, label: `${item.name || nameFromEmail(item.email)} <${item.email}>` })))

async function runMailConnectionTest(scope: MailScope, account: { smtp_user: string; smtp_password: string; smtp_from: string }) {
  const result = await testMailConnection({ scope, smtp_user: account.smtp_user, smtp_password: account.smtp_password, smtp_from: account.smtp_from })
  ElMessage.success(result.message || 'SMTP 连通性测试通过')
}
async function runAdminServerTest(scope: MailScope, server: { smtp_host: string; smtp_port: number; smtp_from: string; use_tls: boolean }, silent = false) {
  const result = await testAdminMailServer({ scope, smtp_host: server.smtp_host, smtp_port: server.smtp_port, smtp_from: server.smtp_from, use_tls: server.use_tls })
  if (!silent) ElMessage.success(result.message || 'SMTP 服务器连通性测试通过')
}
async function testAdminInternal() { if (!settings.value) return; testingAdminInternal.value = true; try { await runAdminServerTest('internal', settings.value.admin.internal_server) } catch (error) { ElMessage.error(errorMessage(error)) } finally { testingAdminInternal.value = false } }
async function testAdminExternal() { if (!settings.value) return; testingAdminExternal.value = true; try { await runAdminServerTest('external', settings.value.admin.external_server) } catch (error) { ElMessage.error(errorMessage(error)) } finally { testingAdminExternal.value = false } }
async function testInternal() { if (!settings.value) return; testingInternal.value = true; try { await runMailConnectionTest('internal', settings.value.user_internal) } catch (error) { ElMessage.error(errorMessage(error)) } finally { testingInternal.value = false } }
async function testUser() { if (!settings.value) return; testingUser.value = true; try { await runMailConnectionTest('external', settings.value.user_external) } catch (error) { ElMessage.error(errorMessage(error)) } finally { testingUser.value = false } }

async function loadExternalAccountContacts(showMessage = true) {
  if (!settings.value) return
  const smtpUser = settings.value.user_external.smtp_user.trim()
  if (!smtpUser) { externalPeople.value = []; externalTemplates.value = []; if (showMessage) ElMessage.warning('请先填写外网 SMTP 用户名'); return }
  loadingExternalContacts.value = true
  try {
    const data = await getExternalAccountContacts(smtpUser) as any
    externalPeople.value = data.contacts_to_people?.length ? data.contacts_to_people : (data.contacts_to || []).map((email: string) => ({ name: nameFromEmail(email), email }))
    externalTemplates.value = editableExternalTemplates(data.contact_templates || [])
    if (showMessage) ElMessage.success('已读取当前外网账号联系人')
  } catch (error) { ElMessage.error(errorMessage(error)) } finally { loadingExternalContacts.value = false }
}
async function handleExternalSmtpUserChange() { await loadExternalAccountContacts(false) }

async function load() {
  loading.value = true
  try {
    settings.value = await getMailSettings()
    internalContactText.value = (settings.value.admin.internal_contacts.contacts.length ? settings.value.admin.internal_contacts.contacts : [...settings.value.admin.internal_contacts.contacts_to, ...settings.value.admin.internal_contacts.contacts_cc]).join('\n')
    externalPeople.value = settings.value.user_external.contacts_to_people?.length ? settings.value.user_external.contacts_to_people : settings.value.user_external.contacts_to.map((email) => ({ name: nameFromEmail(email), email }))
    externalTemplates.value = editableExternalTemplates(settings.value.user_external.contact_templates)
  } catch (error) { ElMessage.error(errorMessage(error)) } finally { loading.value = false }
}

async function saveAdmin() {
  if (!settings.value || !props.session.is_admin) return
  savingAdmin.value = true
  try {
    if (settings.value.admin.internal_server.smtp_host.trim()) await runAdminServerTest('internal', settings.value.admin.internal_server, true)
    if (settings.value.admin.external_server.smtp_host.trim()) await runAdminServerTest('external', settings.value.admin.external_server, true)
    await saveAdminMailSettings({ internal_server: settings.value.admin.internal_server, external_server: settings.value.admin.external_server, internal_contacts: { contacts: splitText(internalContactText.value), contacts_to: [], contacts_cc: [] } })
    ElMessage.success('管理员邮件配置已保存'); emit('changed'); await load()
  } catch (error) { ElMessage.error(errorMessage(error)) } finally { savingAdmin.value = false }
}
async function saveInternal() {
  if (!settings.value) return
  savingInternal.value = true
  try {
    await runMailConnectionTest('internal', settings.value.user_internal)
    await saveUserInternalMailSettings({ smtp_user: settings.value.user_internal.smtp_user, smtp_password: settings.value.user_internal.smtp_password, smtp_from: settings.value.user_internal.smtp_from, contacts_to: [], contacts_cc: [], contact_templates: [] })
    ElMessage.success('个人内网邮件账号已保存'); emit('changed'); await load()
  } catch (error) { ElMessage.error(errorMessage(error)) } finally { savingInternal.value = false }
}
async function saveUser() {
  if (!settings.value) return
  savingUser.value = true
  try {
    await runMailConnectionTest('external', settings.value.user_external)
    const people = cleanPeople(externalPeople.value)
    await saveUserExternalMailSettings({ smtp_user: settings.value.user_external.smtp_user, smtp_password: settings.value.user_external.smtp_password, smtp_from: settings.value.user_external.smtp_from, contacts_to: people.map((item) => item.email), contacts_cc: [], contacts_to_people: people, contacts_cc_people: [], contact_templates: saveableExternalTemplates() })
    ElMessage.success('个人外网邮件设置已保存'); emit('changed'); await load()
  } catch (error) { ElMessage.error(errorMessage(error)) } finally { savingUser.value = false }
}

onMounted(load)
</script>
