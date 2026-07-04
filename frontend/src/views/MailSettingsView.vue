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
        <el-input v-model="internalToText" type="textarea" :rows="4" placeholder="内网收件人，每行或逗号分隔一个邮箱" />
        <el-input v-model="internalCcText" type="textarea" :rows="4" placeholder="内网抄送，每行或逗号分隔一个邮箱" />
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
        </el-input>
        <el-input v-model="settings.user_internal.smtp_from" class="full-row" placeholder="user@company.local">
          <template #prepend>内网发件人</template>
        </el-input>
        <el-input v-model="userInternalToText" type="textarea" :rows="4" placeholder="个人内网收件人模板，每行或逗号分隔一个邮箱" />
        <el-input v-model="userInternalCcText" type="textarea" :rows="4" placeholder="个人内网抄送模板，每行或逗号分隔一个邮箱" />
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
        </el-input>
        <el-input v-model="settings.user_external.smtp_from" class="full-row" placeholder="user@example.com">
          <template #prepend>外网发件人</template>
        </el-input>
        <el-input v-model="externalToText" type="textarea" :rows="4" placeholder="外网收件人，每行或逗号分隔一个邮箱" />
        <el-input v-model="externalCcText" type="textarea" :rows="4" placeholder="外网抄送，每行或逗号分隔一个邮箱" />
      </div>
      <div class="toolbar" style="margin-top: 16px">
        <el-button type="primary" :loading="savingUser" @click="saveUser">保存个人外网设置</el-button>
        <el-button :loading="loading" @click="load">重新读取</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { errorMessage, getMailSettings, saveAdminMailSettings, saveUserExternalMailSettings, saveUserInternalMailSettings } from '../api/http'
import type { MailSettings, SessionInfo } from '../types'

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
const internalToText = ref('')
const internalCcText = ref('')
const userInternalToText = ref('')
const userInternalCcText = ref('')
const externalToText = ref('')
const externalCcText = ref('')

async function load() {
  loading.value = true
  try {
    settings.value = await getMailSettings()
    internalToText.value = settings.value.admin.internal_contacts.contacts_to.join('\n')
    internalCcText.value = settings.value.admin.internal_contacts.contacts_cc.join('\n')
    userInternalToText.value = settings.value.user_internal.contacts_to.join('\n')
    userInternalCcText.value = settings.value.user_internal.contacts_cc.join('\n')
    externalToText.value = settings.value.user_external.contacts_to.join('\n')
    externalCcText.value = settings.value.user_external.contacts_cc.join('\n')
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
        contacts_to: splitText(internalToText.value),
        contacts_cc: splitText(internalCcText.value)
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
    await saveUserInternalMailSettings({
      smtp_user: settings.value.user_internal.smtp_user,
      smtp_password: settings.value.user_internal.smtp_password,
      smtp_from: settings.value.user_internal.smtp_from,
      contacts_to: splitText(userInternalToText.value),
      contacts_cc: splitText(userInternalCcText.value)
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
    await saveUserExternalMailSettings({
      smtp_user: settings.value.user_external.smtp_user,
      smtp_password: settings.value.user_external.smtp_password,
      smtp_from: settings.value.user_external.smtp_from,
      contacts_to: splitText(externalToText.value),
      contacts_cc: splitText(externalCcText.value)
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
