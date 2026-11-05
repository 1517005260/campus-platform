<script setup lang="ts">
/** 申请详情与审批记录：基本信息、各级审批时间线；申请人可撤回待审申请。 */
import { ElMessage, ElMessageBox } from "element-plus";
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { fmtTime } from "@/core/format";
import { showError } from "@/core/http";
import { useAuthStore } from "@/core/auth/store";

import { applicationStatusLabel, recordActionLabel, roomApi, type Application } from "../api";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const applicationId = Number(route.params.id);
const detail = ref<Application | null>(null);
const loading = ref(false);

const isApplicant = () => auth.user?.id === detail.value?.applicant.id;
const canWithdraw = () => detail.value !== null && detail.value.status === "pending" && isApplicant();

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
  await ElMessageBox.confirm("撤回该申请？已通过的占用会一并释放。", "确认");
  try {
    await roomApi.POST("/api/v1/room/applications/{application_id}/withdraw", {
      params: { path: { application_id: applicationId } },
    });
    ElMessage.success("已撤回");
    await router.push("/room/mine");
  } catch (e) {
    showError(e);
  }
}

onMounted(load);
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
      <el-descriptions-item label="教室编号">{{ detail.room_id }}</el-descriptions-item>
      <el-descriptions-item label="开始">{{ fmtTime(detail.start_at) }}</el-descriptions-item>
      <el-descriptions-item label="结束">{{ fmtTime(detail.end_at) }}</el-descriptions-item>
      <el-descriptions-item label="参加人数">{{ detail.attendees }}</el-descriptions-item>
      <el-descriptions-item label="审批进度"
        >{{ detail.current_level }} / {{ detail.total_levels }}</el-descriptions-item
      >
      <el-descriptions-item label="当前级别截止" :span="2">
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

    <div v-if="canWithdraw()" style="margin-top: 16px">
      <el-button type="danger" @click="withdraw">撤回申请</el-button>
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
