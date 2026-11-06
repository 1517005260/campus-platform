<script setup lang="ts">
/** 申请详情与审批记录：基本信息、各级审批时间线；申请人可撤回审批中的申请、取消已通过且未开始的申请。 */
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { fmtTime } from "@/core/format";
import { showError } from "@/core/http";
import { useAuthStore } from "@/core/auth/store";
import { useRooms } from "@/core/rooms";

import { applicationStatusLabel, recordActionLabel, roomApi, type Application } from "../api";
import { withdrawAction, withdrawApplication } from "../withdraw";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const { load: loadRooms, nameOf } = useRooms({ is_whole_bookable: true });

// 路由只匹配数字 id（见模块清单）
const applicationId = Number(route.params.id);
const detail = ref<Application | null>(null);
const loading = ref(false);

const withdrawable = computed(() =>
  detail.value && auth.user?.id === detail.value.applicant.id ? withdrawAction(detail.value) : null,
);

async function load() {
  loading.value = true;
  try {
    const { data } = await roomApi.GET("/api/v1/room/applications/{application_id}", {
      params: { path: { application_id: applicationId } },
    });
    detail.value = data!;
  } catch (e) {
    showError(e);
  } finally {
    loading.value = false;
  }
}

async function withdraw() {
  if (detail.value && (await withdrawApplication(detail.value))) await load();
}

onMounted(() => {
  void load();
  void loadRooms();
});
</script>

<template>
  <div v-loading="loading">
    <el-page-header content="申请详情" @back="router.back()" style="margin-bottom: 16px" />

    <el-descriptions v-if="detail" :column="2" border>
      <el-descriptions-item label="申请号">{{ detail.id }}</el-descriptions-item>
      <el-descriptions-item label="状态">
        <el-tag :type="detail.status === 'approved' ? 'success' : detail.status === 'pending' ? 'warning' : 'info'">
          {{ applicationStatusLabel[detail.status] }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="申请人"
        >{{ detail.applicant.name }}（{{ detail.applicant.username }}）</el-descriptions-item
      >
      <el-descriptions-item label="教室">{{ nameOf(detail.room_id) }}</el-descriptions-item>
      <el-descriptions-item label="开始">{{ fmtTime(detail.start_at) }}</el-descriptions-item>
      <el-descriptions-item label="结束">{{ fmtTime(detail.end_at) }}</el-descriptions-item>
      <el-descriptions-item label="参加人数">{{ detail.attendees }}</el-descriptions-item>
      <el-descriptions-item label="审批进度"
        >{{ detail.current_level }} / {{ detail.total_levels }}</el-descriptions-item
      >
      <el-descriptions-item v-if="detail.status === 'pending'" label="当前级别截止" :span="2">
        {{ detail.deadline_at ? `${fmtTime(detail.deadline_at)}（超时自动撤销）` : "—" }}
      </el-descriptions-item>
      <el-descriptions-item label="用途" :span="2">{{ detail.purpose }}</el-descriptions-item>
    </el-descriptions>

    <el-card header="审批记录" style="margin-top: 16px">
      <el-empty v-if="detail && detail.records.length === 0" description="暂无记录" :image-size="60" />
      <el-timeline v-else-if="detail">
        <el-timeline-item
          v-for="(r, i) in detail.records"
          :key="i"
          :timestamp="fmtTime(r.at)"
          :type="r.action === 'approve' ? 'success' : r.action === 'reject' ? 'danger' : 'info'"
        >
          第 {{ r.level }} 级 · {{ recordActionLabel[r.action] ?? r.action }} ·
          {{ r.approver ? r.approver.name : "系统" }}
          <div v-if="r.comment" class="comment">{{ r.comment }}</div>
        </el-timeline-item>
      </el-timeline>
    </el-card>

    <div v-if="withdrawable" style="margin-top: 16px">
      <el-button type="danger" @click="withdraw">{{ withdrawable.label }}申请</el-button>
    </div>
  </div>
</template>

<style scoped>
.comment {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-top: 4px;
}
</style>
