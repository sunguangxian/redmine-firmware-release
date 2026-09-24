<template>
  <el-dialog :model-value="modelValue" title="补发邮件" width="760px" :close-on-click-modal="!sending" :close-on-press-escape="!sending" :show-close="!sending" @update:model-value="emitVisible">
    <el-alert v-if="attachmentIssue" type="error" :closable="false" show-icon :title="attachmentIssue" />
    <el-alert v-else type="info" :closable="false" show-icon :title="`将附带已发布固件 ${attachmentNames.length} 个`" />
    <ul class="resend-files">
      <li v-for="file in files" :key="`${file.filename}:${file.url || ''}`">{{ file.filename }}</li>
    </ul>
    <div class="form-grid">
      <el-radio-group v-model="mailScope" :disabled="sending" @change="onScopeChange">
        <el-radio-button v-for="scope in scopes" :key="scope.value" :label="scope.value">{{ scope.label }}</el-radio-button>
      </el-radio-group>
      <el-select v-model="selectedTemplateNames" :disabled="sending" multiple filterable placeholder="选择联系人模板" @change="applyContactTemplates">
        <el-option v-for="item in contactTemplates" :key="item.name" :label="item.name" :value="item.name" />
      </el-select>
      <el-select v-model="mailTo" :disabled="sending" multiple filterable placeholder="选择收件人">
        <el-option v-for="item in contactsTo" :key="item" :label="contactLabel(item)" :value="item" />
      </el-select>
      <el-select v-model="mailCc" :disabled="sending" multiple filterable placeholder="选择抄送">
        <el-option v-for="item in contactsCc" :key="item" :label="contactLabel(item)" :value="item" />
      </el-select>
      <el-input v-model="manualMailTo" :disabled="sending" class="full-row" type="textarea" :rows="2" placeholder="手动输入收件人，可用逗号、分号、空格或换行分隔" />
      <el-input v-model="manualMailCc" :disabled="sending" class="full-row" type="textarea" :rows="2" placeholder="手动输入抄送，可用逗号、分号、空格或换行分隔" />
      <el-input v-model="mailSubject" :disabled="sending" class="full-row" placeholder="邮件主题" @input="mailContentEdited = true">
        <template #prepend>邮件主题</template>
      </el-input>
      <el-input v-model="mailBody" :disabled="sending" class="full-row" type="textarea" :rows="10" placeholder="邮件正文" @input="mailContentEdited = true" />
      <div class="full-row toolbar">
        <el-button :disabled="sending" @click="resetMailContent">重新生成邮件内容</el-button>
      </div>
    </div>
    <template #footer>
      <el-button :disabled="sending" @click="emitVisible(false)">取消</el-button>
      <el-button type="primary" :disabled="Boolean(attachmentIssue)" :loading="sending" @click="submit">确认补发</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { errorLogs, errorMessage, getContacts, sendReleaseNotice } from '../api/http'
import type { ContactTemplateConfig, ReleaseFileLink } from '../types'
import { buildMailBody, buildMailSubject, friendlyReleaseError, mergeEmails, publishedAttachmentIssue, splitEmails } from '../utils/releaseUi.js'

const props = defineProps<{
  modelValue: boolean
  projectId: string
  wikiTitle: string
  versionName: string
  releaseDate: string
  commit: string
  changelog: string
  files: ReleaseFileLink[]
  scopes: Array<{ label: string; value: string }>
}>()
const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'sent', value: { ok: boolean; message: string; logs: string[] }): void
  (event: 'failed', value: { message: string; logs: string[] }): void
}>()

const sending = ref(false)
const mailScope = ref('internal')
const contactsTo = ref<string[]>([])
const contactsCc = ref<string[]>([])
const contactTemplates = ref<ContactTemplateConfig[]>([])
const selectedTemplateNames = ref<string[]>([])
const mailTo = ref<string[]>([])
const mailCc = ref<string[]>([])
const manualMailTo = ref('')
const manualMailCc = ref('')
const mailSubject = ref('')
const mailBody = ref('')
const mailContentEdited = ref(false)
const attachmentNames = computed(() => props.files.map((file) => file.filename).filter(Boolean))
const attachmentIssue = computed(() => publishedAttachmentIssue(props.files))

function emitVisible(value: boolean) { if (!sending.value) emit('update:modelValue', value) }
function contactLabel(email: string): string { const key = email.trim().toLowerCase(); for (const template of contactTemplates.value) { const contact = [...template.contacts_to, ...template.contacts_cc].find((item) => item.email.trim().toLowerCase() === key); if (contact) return `${contact.name || contact.email.split('@')[0]} <${contact.email}>` } return email }
function applyContactTemplates() { const selected = contactTemplates.value.filter((item) => selectedTemplateNames.value.includes(item.name)); mailTo.value = mergeEmails(selected.map((item) => item.contacts_to.map((contact) => contact.email))); mailCc.value = mergeEmails(selected.map((item) => item.contacts_cc.map((contact) => contact.email))) }
function generateMailContent() { mailSubject.value = buildMailSubject(mailScope.value, attachmentNames.value, props.versionName, props.releaseDate); mailBody.value = buildMailBody(mailScope.value, attachmentNames.value, props.versionName, props.releaseDate, props.commit, props.changelog) }
function resetMailContent() { mailContentEdited.value = false; generateMailContent() }
async function loadContacts() { try { const data = await getContacts(mailScope.value); contactsTo.value = data.contacts_to; contactsCc.value = data.contacts_cc; contactTemplates.value = data.contact_templates || []; selectedTemplateNames.value = []; mailTo.value = []; mailCc.value = [] } catch (error) { ElMessage.error(friendlyReleaseError(errorMessage(error))) } }
function onScopeChange() { if (!mailContentEdited.value) generateMailContent(); loadContacts() }
function buildFormData(): FormData { const data = new FormData(); data.append('project_id', props.projectId); data.append('wiki_title', props.wikiTitle); data.append('version_name', props.versionName); data.append('mail_scope', mailScope.value); data.append('mail_to', [mailTo.value.join(','), manualMailTo.value].filter(Boolean).join(',')); data.append('mail_cc', [mailCc.value.join(','), manualMailCc.value].filter(Boolean).join(',')); data.append('mail_subject', mailSubject.value); data.append('mail_body', mailBody.value); data.append('send_type', 'resend'); return data }
function noticeError(): string { if (!props.projectId.trim()) return '请选择项目'; if (!props.wikiTitle.trim()) return '请选择要补发邮件的版本'; if (!mergeEmails([mailTo.value, splitEmails(manualMailTo.value)]).length) return '请填写或选择至少一个收件人'; if (!mailSubject.value.trim()) return '请先生成或填写邮件主题'; if (!mailBody.value.trim()) return '请先生成或填写邮件正文'; return '' }
async function submit() { if (sending.value) return; if (attachmentIssue.value) { ElMessage.warning(attachmentIssue.value); return } const error = noticeError(); if (error) { ElMessage.warning(error); return } sending.value = true; try { const result = await sendReleaseNotice(buildFormData()); emit('sent', result); emit('update:modelValue', false) } catch (error) { const message = friendlyReleaseError(errorMessage(error)); const logs = errorLogs(error); emit('failed', { message, logs: logs.length ? logs : [`补发邮件失败：${message}`] }); ElMessage.error(message) } finally { sending.value = false } }
watch(() => props.modelValue, (open) => { if (!open) return; mailContentEdited.value = false; manualMailTo.value = ''; manualMailCc.value = ''; mailScope.value = props.scopes[0]?.value || 'internal'; generateMailContent(); loadContacts() })
</script>

<style scoped>
.resend-files { margin: 12px 0; padding-left: 18px; }
.resend-files li + li { margin-top: 4px; }
</style>
