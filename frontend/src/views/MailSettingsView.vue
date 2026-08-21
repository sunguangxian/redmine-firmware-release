<template>
  <div>
    <el-alert class="card" type="info" :closable="false" show-icon>
      <template #title>邮件服务器由管理员配置；联系人保存时不自动测试 SMTP，测试请点击对应“测试”按钮。</template>
    </el-alert>

    <el-tabs v-model="activeSection" type="border-card">
      <el-tab-pane label="邮件账户" name="accounts">
        <el-card v-if="settings?.is_admin" class="card">
          <template #header>管理员服务器配置</template>
          <div class="form-grid">
            <el-divider class="full-row" content-position="left">内网 SMTP</el-divider>
            <el-input v-model="settings.admin.internal_server.smtp_host" placeholder="内网 SMTP 服务器"><template #prepend>服务器</template></el-input>
            <el-input-number v-model="settings.admin.internal_server.smtp_port" :min="1" :max="65535" style="width: 100%" />
            <el-input v-model="settings.admin.internal_server.smtp_from" class="full-row" placeholder="firmware@company.local"><template #prepend>默认发件人</template></el-input>
            <el-checkbox v-model="settings.admin.internal_server.use_tls" class="full-row">内网使用 STARTTLS；465 端口自动 SSL</el-checkbox>
            <el-divider class="full-row" content-position="left">外网 SMTP</el-divider>
            <el-input v-model="settings.admin.external_server.smtp_host" placeholder="smtp.example.com"><template #prepend>服务器</template></el-input>
            <el-input-number v-model="settings.admin.external_server.smtp_port" :min="1" :max="65535" style="width: 100%" />
            <el-checkbox v-model="settings.admin.external_server.use_tls" class="full-row">外网使用 STARTTLS；465 端口自动 SSL</el-checkbox>
          </div>
          <div class="toolbar mail-settings-actions">
            <el-button :loading="testingAdminInternal" @click="testAdminInternal">测试内网服务器</el-button>
            <el-button :loading="testingAdminExternal" @click="testAdminExternal">测试外网服务器</el-button>
            <el-button type="primary" :loading="savingAdmin" @click="saveAdmin">保存服务器配置</el-button>
          </div>
        </el-card>

        <el-card class="card">
          <template #header>个人内网邮件账号</template>
          <div v-if="settings" class="form-grid">
            <el-input v-model="settings.user_internal.smtp_user" placeholder="内网 SMTP 用户名"><template #prepend>SMTP 用户名</template></el-input>
            <el-input v-model="settings.user_internal.smtp_password" type="password" show-password placeholder="不填写则保留旧密码"><template #prepend>SMTP 密码</template><template #append>{{ settings.user_internal.smtp_password_set ? '已设置' : '未设置' }}</template></el-input>
            <el-input v-model="settings.user_internal.smtp_from" class="full-row" placeholder="user@company.local"><template #prepend>内网发件人</template></el-input>
          </div>
          <div class="toolbar mail-settings-actions">
            <el-button :loading="testingInternal" @click="testInternal">测试内网账号</el-button>
            <el-button type="primary" :loading="savingInternal" @click="saveInternal">保存内网账号</el-button>
          </div>
        </el-card>

        <el-card class="card">
          <template #header>个人外网邮件账号</template>
          <div v-if="settings" class="form-grid">
            <el-input v-model="settings.user_external.smtp_user" placeholder="user@example.com" @change="handleExternalSmtpUserChange"><template #prepend>SMTP 用户名</template></el-input>
            <el-input v-model="settings.user_external.smtp_password" type="password" show-password placeholder="不填写则保留旧密码"><template #prepend>SMTP 密码</template><template #append>{{ settings.user_external.smtp_password_set ? '已设置' : '未设置' }}</template></el-input>
            <el-input v-model="settings.user_external.smtp_from" class="full-row" placeholder="user@example.com"><template #prepend>外网发件人</template></el-input>
          </div>
          <div class="toolbar mail-settings-actions">
            <el-button :loading="testingUser" @click="testUser">测试外网账号</el-button>
            <el-button :loading="loadingExternalContacts" @click="loadExternalAccountContacts()">读取账户数据</el-button>
            <el-button type="primary" :loading="savingUser" @click="saveUser">保存外网账号</el-button>
            <el-button :loading="loading" @click="load">重新读取</el-button>
          </div>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="联系人" name="contacts">
        <el-card class="card">
          <div class="contact-manager-toolbar">
            <el-radio-group v-if="settings?.is_admin" v-model="contactScope">
              <el-radio-button label="internal">内网公共联系人</el-radio-button>
              <el-radio-button label="external">当前外网账户</el-radio-button>
            </el-radio-group>
            <span v-else class="muted">当前外网账户：{{ settings?.user_external.smtp_user || '未配置' }}</span>
            <el-input v-model="contactSearch" clearable placeholder="搜索姓名或邮箱" style="width: 320px" />
            <div style="flex: 1"></div>
            <el-button type="primary" @click="openContactDialog()">新增联系人</el-button>
          </div>

          <el-table :data="pagedContacts" border height="480" empty-text="暂无联系人">
            <el-table-column prop="name" label="姓名" min-width="180" show-overflow-tooltip />
            <el-table-column prop="email" label="邮箱" min-width="320" show-overflow-tooltip />
            <el-table-column label="操作" width="150" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openContactDialog(row)">编辑</el-button>
                <el-button link type="danger" @click="removeContact(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="contact-manager-footer">
            <span class="muted">共 {{ filteredContacts.length }} 个联系人</span>
            <el-pagination v-model:current-page="contactPage" :page-size="contactPageSize" :total="filteredContacts.length" layout="prev, pager, next" background />
            <el-button v-if="contactScope === 'internal'" type="primary" :loading="savingAdmin" @click="saveAdmin">保存内网联系人</el-button>
            <el-button v-else type="primary" :loading="savingUser" @click="saveUser">保存外网联系人</el-button>
          </div>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="联系人组" name="templates">
        <el-card class="card">
          <div class="contact-manager-toolbar">
            <div>
              <div>当前外网账户联系人组</div>
              <div class="muted">用于版本发布时一次选择一组收件人</div>
            </div>
            <div style="flex: 1"></div>
            <el-button type="primary" :disabled="!externalPeople.length" @click="openTemplateDialog()">新增联系人组</el-button>
          </div>
          <el-table :data="externalTemplates" border height="480" empty-text="暂无联系人组">
            <el-table-column prop="name" label="组名" min-width="200" />
            <el-table-column label="成员" min-width="480">
              <template #default="{ row }">
                <el-tag v-for="email in row.emails.slice(0, 6)" :key="email" class="contact-member-tag">{{ contactOptionLabel(email) }}</el-tag>
                <span v-if="row.emails.length > 6" class="muted">另有 {{ row.emails.length - 6 }} 人</span>
              </template>
            </el-table-column>
            <el-table-column label="人数" width="90"><template #default="{ row }">{{ row.emails.length }}</template></el-table-column>
            <el-table-column label="操作" width="150" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openTemplateDialog(row)">编辑</el-button>
                <el-button link type="danger" @click="removeTemplate(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="contact-manager-footer">
            <span class="muted">共 {{ externalTemplates.length }} 个联系人组</span>
            <div style="flex: 1"></div>
            <el-button type="primary" :loading="savingUser" @click="saveUser">保存联系人组</el-button>
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="contactDialogVisible" :title="editingContactIndex < 0 ? '新增联系人' : '编辑联系人'" width="480px">
      <el-form label-position="top">
        <el-form-item label="姓名"><el-input v-model="contactDraft.name" placeholder="联系人姓名" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="contactDraft.email" placeholder="name@example.com" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="contactDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveContactDraft">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="templateDialogVisible" :title="editingTemplateIndex < 0 ? '新增联系人组' : '编辑联系人组'" width="620px">
      <el-form label-position="top">
        <el-form-item label="组名"><el-input v-model="templateDraft.name" placeholder="例如：客户 A、代理商、测试团队" /></el-form-item>
        <el-form-item label="成员">
          <el-select v-model="templateDraft.emails" multiple filterable collapse-tags :max-collapse-tags="4" placeholder="选择联系人" style="width: 100%">
            <el-option v-for="option in externalContactOptions" :key="option.email" :label="option.label" :value="option.email" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="templateDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveTemplateDraft">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { errorMessage, getExternalAccountContacts, getMailSettings, saveAdminMailSettings, saveUserExternalMailSettings, saveUserInternalMailSettings, testAdminMailServer, testMailConnection } from '../api/http'
import type { ContactPersonConfig, ContactTemplateConfig, MailSettings, SessionInfo } from '../types'

const props = defineProps<{ session: SessionInfo }>()
const emit = defineEmits<{ changed: [] }>()
const settings = ref<MailSettings | null>(null)
const activeSection = ref('accounts')
const loading = ref(false)
const savingAdmin = ref(false)
const savingInternal = ref(false)
const savingUser = ref(false)
const testingAdminInternal = ref(false)
const testingAdminExternal = ref(false)
const testingInternal = ref(false)
const testingUser = ref(false)
const loadingExternalContacts = ref(false)
const internalPeople = ref<ContactPersonConfig[]>([])
const externalPeople = ref<ContactPersonConfig[]>([])
const externalTemplates = ref<Array<{ name: string; emails: string[] }>>([])
type MailScope = 'internal' | 'external'
const contactScope = ref<MailScope>(props.session.is_admin ? 'internal' : 'external')
const contactSearch = ref('')
const contactPage = ref(1)
const contactPageSize = 12
const contactDialogVisible = ref(false)
const editingContactIndex = ref(-1)
const contactDraft = ref<ContactPersonConfig>({ name: '', email: '' })
const templateDialogVisible = ref(false)
const editingTemplateIndex = ref(-1)
const templateDraft = ref<{ name: string; emails: string[] }>({ name: '', emails: [] })

function nameFromEmail(email: string): string { return email.split('@')[0] || email }
function cleanPeople(items: ContactPersonConfig[]): ContactPersonConfig[] { const seen = new Set<string>(); const result: ContactPersonConfig[] = []; items.forEach((item) => { const email = item.email.trim(); const key = email.toLowerCase(); if (!email.includes('@') || seen.has(key)) return; seen.add(key); result.push({ name: item.name.trim() || nameFromEmail(email), email }) }); return result }
function emailToPerson(email: string): ContactPersonConfig { return externalPeople.value.find((item) => item.email.trim().toLowerCase() === email.trim().toLowerCase()) || { name: nameFromEmail(email), email } }
function editableExternalTemplates(items: ContactTemplateConfig[]) { return (items || []).map((item) => ({ name: item.name, emails: item.contacts_to.map((contact) => contact.email) })) }
function saveableExternalTemplates(): ContactTemplateConfig[] { return externalTemplates.value.map((item) => ({ name: item.name.trim(), contacts_to: item.emails.map(emailToPerson), contacts_cc: [] })).filter((item) => item.name) }
const externalContactOptions = computed(() => cleanPeople(externalPeople.value).map((item) => ({ ...item, label: `${item.name || nameFromEmail(item.email)} <${item.email}>` })))
const activePeople = computed(() => contactScope.value === 'internal' ? internalPeople.value : externalPeople.value)
const filteredContacts = computed(() => {
  const keyword = contactSearch.value.trim().toLowerCase()
  if (!keyword) return activePeople.value
  return activePeople.value.filter((item) => item.name.toLowerCase().includes(keyword) || item.email.toLowerCase().includes(keyword))
})
const pagedContacts = computed(() => {
  const start = (contactPage.value - 1) * contactPageSize
  return filteredContacts.value.slice(start, start + contactPageSize)
})

function contactOptionLabel(email: string): string { return externalContactOptions.value.find((item) => item.email.toLowerCase() === email.toLowerCase())?.label || email }

function openContactDialog(item?: ContactPersonConfig) {
  editingContactIndex.value = item ? activePeople.value.indexOf(item) : -1
  contactDraft.value = item ? { ...item } : { name: '', email: '' }
  contactDialogVisible.value = true
}

function saveContactDraft() {
  const email = contactDraft.value.email.trim()
  if (!email || !email.includes('@')) return ElMessage.warning('请填写有效的联系人邮箱')
  const list = activePeople.value
  const duplicate = list.some((item, index) => index !== editingContactIndex.value && item.email.trim().toLowerCase() === email.toLowerCase())
  if (duplicate) return ElMessage.warning('该邮箱已在联系人列表中')
  const next = { name: contactDraft.value.name.trim() || nameFromEmail(email), email }
  if (editingContactIndex.value >= 0) {
    const oldEmail = list[editingContactIndex.value].email
    list.splice(editingContactIndex.value, 1, next)
    if (contactScope.value === 'external' && oldEmail.toLowerCase() !== email.toLowerCase()) {
      externalTemplates.value.forEach((item) => { item.emails = item.emails.map((value) => value.toLowerCase() === oldEmail.toLowerCase() ? email : value) })
    }
  } else {
    list.push(next)
  }
  contactDialogVisible.value = false
}

async function removeContact(item: ContactPersonConfig) {
  try {
    await ElMessageBox.confirm(`确认删除联系人“${item.name || item.email}”吗？`, '删除联系人', { type: 'warning' })
  } catch {
    return
  }
  const index = activePeople.value.indexOf(item)
  if (index >= 0) activePeople.value.splice(index, 1)
  if (contactScope.value === 'external') {
    externalTemplates.value.forEach((template) => { template.emails = template.emails.filter((email) => email.toLowerCase() !== item.email.toLowerCase()) })
  }
  const lastPage = Math.max(1, Math.ceil(filteredContacts.value.length / contactPageSize))
  contactPage.value = Math.min(contactPage.value, lastPage)
}

function openTemplateDialog(item?: { name: string; emails: string[] }) {
  editingTemplateIndex.value = item ? externalTemplates.value.indexOf(item) : -1
  templateDraft.value = item ? { name: item.name, emails: [...item.emails] } : { name: '', emails: [] }
  templateDialogVisible.value = true
}

function saveTemplateDraft() {
  const name = templateDraft.value.name.trim()
  if (!name) return ElMessage.warning('请填写联系人组名称')
  if (!templateDraft.value.emails.length) return ElMessage.warning('请至少选择一个联系人')
  const duplicate = externalTemplates.value.some((item, index) => index !== editingTemplateIndex.value && item.name.trim().toLowerCase() === name.toLowerCase())
  if (duplicate) return ElMessage.warning('联系人组名称已存在')
  const next = { name, emails: [...templateDraft.value.emails] }
  if (editingTemplateIndex.value >= 0) externalTemplates.value.splice(editingTemplateIndex.value, 1, next)
  else externalTemplates.value.push(next)
  templateDialogVisible.value = false
}

async function removeTemplate(item: { name: string; emails: string[] }) {
  try {
    await ElMessageBox.confirm(`确认删除联系人组“${item.name}”吗？`, '删除联系人组', { type: 'warning' })
  } catch {
    return
  }
  const index = externalTemplates.value.indexOf(item)
  if (index >= 0) externalTemplates.value.splice(index, 1)
}

async function runMailConnectionTest(scope: MailScope, account: { smtp_user: string; smtp_password: string; smtp_from: string }) { const result = await testMailConnection({ scope, smtp_user: account.smtp_user, smtp_password: account.smtp_password, smtp_from: account.smtp_from }); ElMessage.success(result.message || 'SMTP 连通性测试通过') }
async function runAdminServerTest(scope: MailScope, server: { smtp_host: string; smtp_port: number; smtp_from: string; use_tls: boolean }) { const result = await testAdminMailServer({ scope, smtp_host: server.smtp_host, smtp_port: server.smtp_port, smtp_from: server.smtp_from, use_tls: server.use_tls }); ElMessage.success(result.message || 'SMTP 服务器连通性测试通过') }
async function testAdminInternal() { if (!settings.value) return; testingAdminInternal.value = true; try { await runAdminServerTest('internal', settings.value.admin.internal_server) } catch (error) { ElMessage.error(errorMessage(error)) } finally { testingAdminInternal.value = false } }
async function testAdminExternal() { if (!settings.value) return; testingAdminExternal.value = true; try { await runAdminServerTest('external', settings.value.admin.external_server) } catch (error) { ElMessage.error(errorMessage(error)) } finally { testingAdminExternal.value = false } }
async function testInternal() { if (!settings.value) return; testingInternal.value = true; try { await runMailConnectionTest('internal', settings.value.user_internal) } catch (error) { ElMessage.error(errorMessage(error)) } finally { testingInternal.value = false } }
async function testUser() { if (!settings.value) return; testingUser.value = true; try { await runMailConnectionTest('external', settings.value.user_external) } catch (error) { ElMessage.error(errorMessage(error)) } finally { testingUser.value = false } }

async function loadExternalAccountContacts(showMessage = true) { if (!settings.value) return; const smtpUser = settings.value.user_external.smtp_user.trim(); if (!smtpUser) { externalPeople.value = []; externalTemplates.value = []; if (showMessage) ElMessage.warning('请先填写外网 SMTP 用户名'); return } loadingExternalContacts.value = true; try { const data = await getExternalAccountContacts(smtpUser) as any; externalPeople.value = data.contacts_to_people?.length ? data.contacts_to_people : (data.contacts_to || []).map((email: string) => ({ name: nameFromEmail(email), email })); externalTemplates.value = editableExternalTemplates(data.contact_templates || []); if (showMessage) ElMessage.success('已读取当前外网账号联系人') } catch (error) { ElMessage.error(errorMessage(error)) } finally { loadingExternalContacts.value = false } }
async function handleExternalSmtpUserChange() { await loadExternalAccountContacts(false) }

async function load() { loading.value = true; try { settings.value = await getMailSettings(); internalPeople.value = settings.value.admin.internal_contacts.contacts_people?.length ? settings.value.admin.internal_contacts.contacts_people : settings.value.admin.internal_contacts.contacts_to.map((email) => ({ name: nameFromEmail(email), email })); externalPeople.value = settings.value.user_external.contacts_to_people?.length ? settings.value.user_external.contacts_to_people : settings.value.user_external.contacts_to.map((email) => ({ name: nameFromEmail(email), email })); externalTemplates.value = editableExternalTemplates(settings.value.user_external.contact_templates) } catch (error) { ElMessage.error(errorMessage(error)) } finally { loading.value = false } }
async function saveAdmin() { if (!settings.value || !props.session.is_admin) return; savingAdmin.value = true; try { const people = cleanPeople(internalPeople.value); await saveAdminMailSettings({ internal_server: settings.value.admin.internal_server, external_server: settings.value.admin.external_server, internal_contacts: { contacts: people.map((item) => item.email), contacts_to: people.map((item) => item.email), contacts_cc: [], contacts_people: people } }); ElMessage.success('管理员邮件配置已保存'); emit('changed'); await load() } catch (error) { ElMessage.error(errorMessage(error)) } finally { savingAdmin.value = false } }
async function saveInternal() { if (!settings.value) return; savingInternal.value = true; try { await saveUserInternalMailSettings({ smtp_user: settings.value.user_internal.smtp_user, smtp_password: settings.value.user_internal.smtp_password, smtp_from: settings.value.user_internal.smtp_from, contacts_to: settings.value.user_internal.contacts_to, contacts_cc: settings.value.user_internal.contacts_cc, contact_templates: settings.value.user_internal.contact_templates }); ElMessage.success('个人内网邮件账号已保存'); emit('changed'); await load() } catch (error) { ElMessage.error(errorMessage(error)) } finally { savingInternal.value = false } }
async function saveUser() { if (!settings.value) return; savingUser.value = true; try { const people = cleanPeople(externalPeople.value); await saveUserExternalMailSettings({ smtp_user: settings.value.user_external.smtp_user, smtp_password: settings.value.user_external.smtp_password, smtp_from: settings.value.user_external.smtp_from, contacts_to: people.map((item) => item.email), contacts_cc: [], contacts_to_people: people, contacts_cc_people: [], contact_templates: saveableExternalTemplates() }); ElMessage.success('个人外网邮件设置已保存'); emit('changed'); await load() } catch (error) { ElMessage.error(errorMessage(error)) } finally { savingUser.value = false } }

watch([contactScope, contactSearch], () => { contactPage.value = 1 })
onMounted(load)
</script>
