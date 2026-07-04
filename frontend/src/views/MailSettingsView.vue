<template>
  <div>
    <el-alert class="card" type="info" :closable="false" show-icon>
      <template #title>
        邮件服务器和内网联系人只允许 Redmine 管理员修改；每个用户维护自己的内网 SMTP 账号，外网账号和外网联系人。
      </template>
    </el-alert>

    <el-card v-if="settings?.is_admin" class="card">
      <template #header>管理员配置</template>
      <div class="form-grid">
        <el-divider class="full-row" content-position="left">内网 SMTP</el-divider>
        <el-input v-model="settings.admin.internal_server.smtp_host" placeholder="内网 SMTP 服务器">
          <template #prepend>服务器</template>
        </el-input>
        <el-input-number v-model="settings.admin.internal_server.smtp_port" :min="1" :max="65535" style="width: 100%" />
        <el-input v-model="settings.admin.internal_server.smtp_from" class="full-row" placeholder="firmware@company.local">
          <template #prepend>默认发件人</template>
        </el-input>
        <el-checkbox v-model="settings.admin.internal_server.use_tls" class="full-row">内网使用 STARTTLS；465 端口自动 SSL</el-checkbox>

        <el-divider class="full-row" content-position="left">外网 SMTP 服务器</el-divider>
        <el-input v-model="settings.admin.external_server.smtp_host" placeholder="smtp.example.com">
          <template #prepend>服务器</template>
        </el-input>
        <el-input-number v-model="settings.admin.external_server.smtp_port" :min="1" :max="65535" style="width: 100%" />
        <el-checkbox v-model="settings.admin.external_server.use_tls" class="full-row">外网使用 STARTTLS；465 端口自动 SSL</el-checkbox>

        <el-divider class="full-row" content-position="left">内网联系人</el-divider>
        <el-input v-model="internalContactText" class="full-row" type="textarea" :rows="5" placeholder="内网联系人，每行或逗号分隔一个邮箱" />
      </div>
      <div class="toolbar" style="margin-top: 16px">
        <el-button type="primary" :loading="savingAdmin" @click="saveAdmin">保存管理员邮件配置</el-button>
      </div>
    </el-card>

    <el-card class="card">
      <template #header>个人内网邮件账号</template>
      <div v-if="settings" class="form-grid">
        <el-input v-model="settings.user_internal.smtp_user" placeholder="内网 SMTP 用户名">
          <template #prepend>SMTP 用户名</template>
        </el-input>
        <el-input v-model="settings.user_internal.smtp_password" type="password" show-password placeholder="不填写则保留旧密码">
          <template #prepend>SMTP 密码</template>
          <template #append>{{ settings.user_internal.smtp_password_set ? '已设置' : '未设置' }}</template>
        </el-input>
        <el-input v-model="settings.user_internal.smtp_from" class="full-row" placeholder="user@company.local">
          <template #prepend>内网发件人</template>
        </el-input>
        <div class="full-row contact-template-list">
          <div v-for="(item, index) in userInternalTemplates" :key="index" class="contact-template-item">
            <el-input v-model="item.name" placeholder="模块名，例如：驱动 / APP / 测试">
              <template #prepend>模块</template>
            </el-input>
            <div class="contact-list">
              <div class="contact-list-title">收件人</div>
              <div v-for="(contact, contactIndex) in item.contactsTo" :key="contactIndex" class="contact-row">
                <el-input v-model="contact.name" placeholder="名称" />
                <el-select v-model="contact.email" filterable allow-create default-first-option placeholder="邮箱" @change="fillContactName(contact, internalContactOptions)">
                  <el-option v-for="option in internalContactOptions" :key="option.email" :label="option.label" :value="option.email" />
                </el-select>
                <el-button @click="item.contactsTo.splice(contactIndex, 1)">删除</el-button>
              </div>
              <el-button @click="addContact(item.contactsTo)">添加收件人</el-button>
            </div>
            <div class="contact-list">
              <div class="contact-list-title">抄送</div>
              <div v-for="(contact, contactIndex) in item.contactsCc" :key="contactIndex" class="contact-row">
                <el-input v-model="contact.name" placeholder="名称" />
                <el-select v-model="contact.email" filterable allow-create default-first-option placeholder="邮箱" @change="fillContactName(contact, internalContactOptions)">
                  <el-option v-for="option in internalContactOptions" :key="option.email" :label="option.label" :value="option.email" />
                </el-select>
                <el-button @click="item.contactsCc.splice(contactIndex, 1)">删除</el-button>
              </div>
              <el-button @click="addContact(item.contactsCc)">添加抄送</el-button>
            </div>
            <el-button @click="userInternalTemplates.splice(index, 1)">删除模板</el-button>
          </div>
          <el-button @click="addTemplate(userInternalTemplates)">新增内网联系人模板</el-button>
        </div>
      </div>
      <div class="toolbar" style="margin-top: 16px">
        <el-button type="primary" :loading="savingInternal" @click="saveInternal">保存个人内网账号和联系人</el-button>
      </div>
    </el-card>

    <el-card class="card">
      <template #header>个人外网邮件账号和联系人</template>
      <div v-if="settings" class="form-grid">
        <el-input v-model="settings.user_external.smtp_user" placeholder="user@example.com">
          <template #prepend>SMTP 用户名</template>
        </el-input>
        <el-input v-model="settings.user_external.smtp_password" type="password" show-password placeholder="不填写则保留旧密码">
          <template #prepend>SMTP 密码</template>
          <template #append>{{ settings.user_external.smtp_password_set ? '已设置' : '未设置' }}</template>
        </el-input>
        <el-input v-model="settings.user_external.smtp_from" class="full-row" placeholder="user@example.com">
          <template #prepend>外网发件人</template>
        </el-input>
        <div class="full-row contact-template-list">
          <div v-for="(item, index) in userExternalTemplates" :key="index" class="contact-template-item">
            <el-input v-model="item.name" placeholder="模块名，例如：客户A / 代理商 / 测试">
              <template #prepend>模块</template>
            </el-input>
            <div class="contact-list">
              <div class="contact-list-title">收件人</div>
              <div v-for="(contact, contactIndex) in item.contactsTo" :key="contactIndex" class="contact-row">
                <el-input v-model="contact.name" placeholder="名称" />
                <el-select v-model="contact.email" filterable allow-create default-first-option placeholder="邮箱" @change="fillContactName(contact, externalContactOptions)">
                  <el-option v-for="option in externalContactOptions" :key="option.email" :label="option.label" :value="option.email" />
                </el-select>
                <el-button @click="item.contactsTo.splice(contactIndex, 1)">删除</el-button>
              </div>
              <el-button @click="addContact(item.contactsTo)">添加收件人</el-button>
            </div>
            <div class="contact-list">
              <div class="contact-list-title">抄送</div>
              <div v-for="(contact, contactIndex) in item.contactsCc" :key="contactIndex" class="contact-row">
                <el-input v-model="contact.name" placeholder="名称" />
                <el-select v-model="contact.email" filterable allow-create default-first-option placeholder="邮箱" @change="fillContactName(contact, externalContactOptions)">
                  <el-option v-for="option in externalContactOptions" :key="option.email" :label="option.label" :value="option.email" />
                </el-select>
                <el-button @click="item.contactsCc.splice(contactIndex, 1)">删除</el-button>
              </div>
              <el-button @click="addContact(item.contactsCc)">添加抄送</el-button>
            </div>
            <el-button @click="userExternalTemplates.splice(index, 1)">删除模板</el-button>
          </div>
          <el-button @click="addTemplate(userExternalTemplates)">新增外网联系人模板</el-button>
        </div>
      </div>
      <div class="toolbar" style="margin-top: 16px">
        <el-button type="primary" :loading="savingUser" @click="saveUser">保存个人外网设置</el-button>
        <el-button :loading="loading" @click="load">重新读取</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { errorMessage, getMailSettings, saveAdminMailSettings, saveUserExternalMailSettings, saveUserInternalMailSettings } from '../api/http'
import type { ContactTemplateConfig, MailSettings, SessionInfo } from '../types'

function splitText(text: string): string[] {
  return text.split(/[\n,;，；\s]+/).map((item) => item.trim()).filter((item) => item.includes('@'))
}

const props = defineProps<{ session: SessionInfo }>()
const emit = defineEmits<{ changed: [] }>()
const settings = ref<MailSettings | null>(null)
const loading = ref(false)
const savingAdmin = ref(false)
const savingInternal = ref(false)
const savingUser = ref(false)
const internalContactText = ref('')
type EditableContact = { name: string; email: string }
type EditableTemplate = { name: string; contactsTo: EditableContact[]; contactsCc: EditableContact[] }
type ContactOption = { name: string; email: string; label: string }
const userInternalTemplates = ref<EditableTemplate[]>([])
const userExternalTemplates = ref<EditableTemplate[]>([])

function editableTemplates(items: ContactTemplateConfig[]): EditableTemplate[] {
  return (items || []).map((item) => ({
    name: item.name,
    contactsTo: item.contacts_to.map((contact) => ({ name: contact.name, email: contact.email })),
    contactsCc: item.contacts_cc.map((contact) => ({ name: contact.name, email: contact.email }))
  }))
}

function saveableTemplates(items: EditableTemplate[]): ContactTemplateConfig[] {
  return items
    .map((item) => ({
      name: item.name.trim(),
      contacts_to: cleanContacts(item.contactsTo),
      contacts_cc: cleanContacts(item.contactsCc)
    }))
    .filter((item) => item.name)
}

function nameFromEmail(email: string): string {
  return email.split('@')[0] || email
}

function cleanContacts(items: EditableContact[]): EditableContact[] {
  const seen = new Set<string>()
  const result: EditableContact[] = []
  ;(items || []).forEach((item) => {
    const email = item.email.trim()
    const key = email.toLowerCase()
    if (!email.includes('@') || seen.has(key)) return
    seen.add(key)
    result.push({ name: item.name.trim() || nameFromEmail(email), email })
  })
  return result
}

function flattenTemplates(items: ContactTemplateConfig[], key: 'contacts_to' | 'contacts_cc'): string[] {
  const seen = new Set<string>()
  const result: string[] = []
  items.forEach((item) => {
    item[key].forEach((contact) => {
      const email = contact.email.trim()
      const lower = email.toLowerCase()
      if (email && !seen.has(lower)) {
        seen.add(lower)
        result.push(email)
      }
    })
  })
  return result
}

function addTemplate(items: EditableTemplate[]) {
  items.push({ name: '', contactsTo: [], contactsCc: [] })
}

function addContact(items: EditableContact[]) {
  items.push({ name: '', email: '' })
}

function contactLabel(contact: EditableContact): string {
  return `${contact.name || nameFromEmail(contact.email)} <${contact.email}>`
}

function collectOptions(templates: EditableTemplate[], extra: string[] = []): ContactOption[] {
  const seen = new Set<string>()
  const result: ContactOption[] = []
  const contacts = [
    ...extra.map((email) => ({ name: nameFromEmail(email), email })),
    ...templates.flatMap((item) => [...item.contactsTo, ...item.contactsCc])
  ]
  contacts.forEach((contact) => {
    const value = contact.email.trim()
    const key = value.toLowerCase()
    if (value && value.includes('@') && !seen.has(key)) {
      seen.add(key)
      const clean = { name: contact.name.trim() || nameFromEmail(value), email: value }
      result.push({ ...clean, label: contactLabel(clean) })
    }
  })
  return result
}

function fillContactName(contact: EditableContact, options: ContactOption[]) {
  if (contact.name.trim()) return
  const option = options.find((item) => item.email.toLowerCase() === contact.email.trim().toLowerCase())
  contact.name = option?.name || nameFromEmail(contact.email)
}

const internalContactOptions = computed(() =>
  collectOptions(userInternalTemplates.value, splitText(internalContactText.value))
)
const externalContactOptions = computed(() => collectOptions(userExternalTemplates.value))

async function load() {
  loading.value = true
  try {
    settings.value = await getMailSettings()
    internalContactText.value = (
      settings.value.admin.internal_contacts.contacts.length
        ? settings.value.admin.internal_contacts.contacts
        : [...settings.value.admin.internal_contacts.contacts_to, ...settings.value.admin.internal_contacts.contacts_cc]
    ).join('\n')
    userInternalTemplates.value = editableTemplates(settings.value.user_internal.contact_templates)
    userExternalTemplates.value = editableTemplates(settings.value.user_external.contact_templates)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    loading.value = false
  }
}

async function saveAdmin() {
  if (!settings.value || !props.session.is_admin) return
  savingAdmin.value = true
  try {
    await saveAdminMailSettings({
      internal_server: settings.value.admin.internal_server,
      external_server: settings.value.admin.external_server,
      internal_contacts: {
        contacts: splitText(internalContactText.value),
        contacts_to: [],
        contacts_cc: []
      }
    })
    ElMessage.success('管理员邮件配置已保存')
    emit('changed')
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    savingAdmin.value = false
  }
}

async function saveInternal() {
  if (!settings.value) return
  savingInternal.value = true
  try {
    const templates = saveableTemplates(userInternalTemplates.value)
    await saveUserInternalMailSettings({
      smtp_user: settings.value.user_internal.smtp_user,
      smtp_password: settings.value.user_internal.smtp_password,
      smtp_from: settings.value.user_internal.smtp_from,
      contacts_to: flattenTemplates(templates, 'contacts_to'),
      contacts_cc: flattenTemplates(templates, 'contacts_cc'),
      contact_templates: templates
    })
    ElMessage.success('个人内网邮件账号和联系人已保存')
    emit('changed')
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    savingInternal.value = false
  }
}

async function saveUser() {
  if (!settings.value) return
  savingUser.value = true
  try {
    const templates = saveableTemplates(userExternalTemplates.value)
    await saveUserExternalMailSettings({
      smtp_user: settings.value.user_external.smtp_user,
      smtp_password: settings.value.user_external.smtp_password,
      smtp_from: settings.value.user_external.smtp_from,
      contacts_to: flattenTemplates(templates, 'contacts_to'),
      contacts_cc: flattenTemplates(templates, 'contacts_cc'),
      contact_templates: templates
    })
    ElMessage.success('个人外网邮件设置已保存')
    emit('changed')
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    savingUser.value = false
  }
}

onMounted(load)
</script>
