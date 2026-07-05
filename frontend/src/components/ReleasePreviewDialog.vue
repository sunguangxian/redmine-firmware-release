<template>
  <el-dialog v-model="visible" :title="title" width="860px" destroy-on-close>
    <template v-if="plan">
      <el-descriptions :column="2" border>
        <el-descriptions-item label="操作">{{ plan.action }}</el-descriptions-item>
        <el-descriptions-item label="项目">{{ plan.project_id }}</el-descriptions-item>
        <el-descriptions-item label="版本">{{ plan.version_name }}</el-descriptions-item>
        <el-descriptions-item label="日期">{{ plan.release_date }}</el-descriptions-item>
        <el-descriptions-item label="目标页面" :span="2">{{ plan.display_target || plan.wiki_title || plan.target_page }}</el-descriptions-item>
        <el-descriptions-item label="Redmine Version">{{ plan.version_plan }}</el-descriptions-item>
        <el-descriptions-item label="附件策略">{{ plan.attachment_plan }}</el-descriptions-item>
        <el-descriptions-item label="邮件">{{ plan.notice_enabled ? `${plan.mail_scope_label}，收件人 ${plan.mail_to_count} 个，抄送 ${plan.mail_cc_count} 个` : '不发送' }}</el-descriptions-item>
      </el-descriptions>

      <el-alert v-if="plan.warnings?.length" class="preview-section" type="warning" :closable="false" show-icon>
        <template #title>注意事项</template>
        <div v-for="item in plan.warnings" :key="item">- {{ item }}</div>
      </el-alert>

      <div class="preview-section">
        <div class="preview-title">新附件</div>
        <el-table :data="plan.files || plan.new_files || []" border size="small" max-height="220">
          <el-table-column prop="filename" label="文件名" min-width="260" show-overflow-tooltip />
          <el-table-column prop="size" label="大小" width="120" />
          <el-table-column prop="sha256" label="SHA256" min-width="320" show-overflow-tooltip />
        </el-table>
      </div>

      <div v-if="plan.logs?.length" class="preview-section release-log">
        <div class="preview-title">预览日志</div>
        <div v-for="(item, index) in plan.logs" :key="index">{{ index + 1 }}. {{ item }}</div>
      </div>
    </template>
    <template #footer>
      <el-button @click="emitCancel">取消</el-button>
      <el-button type="primary" @click="emitConfirm">确认执行</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ReleasePlan } from '../api/http'

const props = defineProps<{ modelValue: boolean; plan: ReleasePlan | null; title?: string }>()
const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'confirm'): void
  (event: 'cancel'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

function emitConfirm() {
  emit('confirm')
  emit('update:modelValue', false)
}

function emitCancel() {
  emit('cancel')
  emit('update:modelValue', false)
}
</script>

<style scoped>
.preview-section { margin-top: 12px; }
.preview-title { font-weight: 600; margin-bottom: 8px; }
</style>
