<script setup lang="ts">
/** 待我审批：通过/驳回（可填审批意见），查看申请详情与审批进度。 */
import { ElMessage, ElMessageBox } from "element-plus";
import { onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";

import PaginatedTable from "@/core/components/PaginatedTable.vue";
import { fmtTime } from "@/core/format";
import { showError } from "@/core/http";

import { roomApi, type ApplicationForApprover } from "../api";

const router = useRouter();
const items = ref<ApplicationForApprover[]>([]);
const loading = ref(false);
const total = ref(0);
const page = ref(1);
const size = ref(10);

async function load() {
  loading.value = true;
  try {
    const { data } = await roomApi.GET("/api/v1/room/approvals/todo", {
      params: { query: { page: page.value, size: size.value } },
    });
    items.value = data!.items;
    total.value = data!.total;
  } catch (e) {
    showError(e);
  } finally {
    loading.value = false;
  }
}

async function act(row: ApplicationForApprover, action: "approve" | "reject") {
  const tip = action === "approve" ? "通过该申请？（可填审批意见）" : "驳回该申请？（可填驳回原因）";
  let comment: string | undefined;
  try {
    const { value } = await ElMessageBox.prompt(tip, action === "approve" ? "通过" : "驳回", {
      inputType: "textarea",
    });
    comment = value || undefined;
  } catch {
    return; // 用户取消
  }
  try {
    await roomApi.POST(`/api/v1/room/applications/{application_id}/${action}`, {
      params: { path: { application_id: row.id } },
      body: { comment: comment ?? null },
    });
    ElMessage.success(action === "approve" ? "已通过" : "已驳回");
    await load();
  } catch (e) {
    showError(e);
  }
}

watch([page, size], () => void load());
onMounted(load);
</script>

<template>
  <PaginatedTable :data="items" :loading="loading" :total="total" v-model:page="page" v-model:size="size">
    <el-table-column label="申请号" prop="id" width="80" />
    <el-table-column label="申请人" prop="applicant.name" width="100" />
    <el-table-column label="教室编号" prop="room_id" width="90" />
    <el-table-column label="开始">
      <template #default="{ row }">{{ fmtTime(row.start_at) }}</template>
    </el-table-column>
    <el-table-column label="用途" prop="purpose" show-overflow-tooltip />
    <el-table-column label="影响预约" width="90">
      <template #default="{ row }">
        <el-tag v-if="row.affected_reservations > 0" size="small" type="warning">
          {{ row.affected_reservations }} 条
        </el-tag>
        <span v-else>无</span>
      </template>
    </el-table-column>
    <el-table-column label="审批截止">
      <template #default="{ row }">{{ fmtTime(row.deadline_at) }}</template>
    </el-table-column>
    <el-table-column label="操作" width="200">
      <template #default="{ row }">
        <el-button size="small" link type="primary" @click="router.push(`/room/applications/${row.id}`)">
          详情
        </el-button>
        <el-button size="small" type="primary" @click="act(row, 'approve')">通过</el-button>
        <el-button size="small" type="danger" @click="act(row, 'reject')">驳回</el-button>
      </template>
    </el-table-column>
  </PaginatedTable>
</template>
