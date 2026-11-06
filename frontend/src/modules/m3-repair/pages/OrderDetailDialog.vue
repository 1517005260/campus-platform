<script setup lang="ts">
/** 工单详情对话框：基本信息 + 处理时间线。 */
import { fmtTime } from "@/core/format";

import { orderStatusLabel, timelineActionLabel, type WorkOrder } from "../api";

const visible = defineModel<boolean>({ required: true });
defineProps<{ order: WorkOrder | null }>();

/** 只把 http(s) 链接渲染成可点击的链接，其他内容（如 javascript:）按文本显示 */
const isWebLink = (url: string) => /^https?:\/\//i.test(url);
</script>

<template>
  <el-dialog :model-value="visible" title="工单详情" width="640px" @update:model-value="visible = $event">
    <template v-if="order">
      <el-descriptions :column="2" border>
        <el-descriptions-item label="工单号">{{ order.id }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ orderStatusLabel[order.status] }}</el-descriptions-item>
        <el-descriptions-item label="报修人">{{ order.reporter.name }}</el-descriptions-item>
        <el-descriptions-item label="维修人">{{ order.assignee?.name ?? "未派单" }}</el-descriptions-item>
        <el-descriptions-item label="教室编号">{{ order.room_id }}</el-descriptions-item>
        <el-descriptions-item label="座位">
          {{ order.seat_id ? `#${order.seat_id}` : "教室整体" }}
        </el-descriptions-item>
        <el-descriptions-item label="分类">{{ order.category }}</el-descriptions-item>
        <el-descriptions-item label="下架教室">{{ order.blocks_room ? "是" : "否" }}</el-descriptions-item>
        <el-descriptions-item label="处理截止">
          {{ order.deadline_at ? fmtTime(order.deadline_at) : "—" }}
        </el-descriptions-item>
        <el-descriptions-item label="升级次数">{{ order.escalation_level }}</el-descriptions-item>
        <el-descriptions-item label="描述" :span="2">{{ order.description }}</el-descriptions-item>
        <el-descriptions-item v-if="order.photos.length > 0" label="照片" :span="2">
          <template v-for="p in order.photos" :key="p">
            <a v-if="isWebLink(p)" :href="p" target="_blank" rel="noopener noreferrer" class="photo">{{ p }}</a>
            <span v-else class="photo">{{ p }}</span>
          </template>
        </el-descriptions-item>
        <el-descriptions-item label="评分">
          {{ order.rating !== null ? `${order.rating} / 5` : "未评价" }}
        </el-descriptions-item>
      </el-descriptions>

      <el-card header="处理时间线" style="margin-top: 16px">
        <el-timeline>
          <el-timeline-item
            v-for="(t, i) in order.timeline"
            :key="i"
            :timestamp="fmtTime(t.at)"
            :type="
              ['accept', 'admin_accept'].includes(t.action) ? 'success' : t.action === 'reject' ? 'danger' : 'primary'
            "
          >
            {{ timelineActionLabel[t.action] }} · {{ t.actor ? t.actor.name : "系统" }}
            <span v-if="t.from_status || t.to_status" class="transition">
              （{{ t.from_status ? orderStatusLabel[t.from_status] : "—" }} →
              {{ t.to_status ? orderStatusLabel[t.to_status] : "—" }}）
            </span>
            <div v-if="t.note" class="note">{{ t.note }}</div>
          </el-timeline-item>
        </el-timeline>
      </el-card>
    </template>
  </el-dialog>
</template>

<style scoped>
.photo {
  display: block;
  word-break: break-all;
}
a.photo {
  color: var(--el-color-primary);
}
.transition {
  color: var(--el-text-color-secondary);
}
.note {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-top: 4px;
}
</style>
