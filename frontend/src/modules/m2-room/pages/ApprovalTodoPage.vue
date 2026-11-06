<script setup lang="ts">
/** 待我审批：通过/驳回（可填审批意见），查看申请详情与审批进度。 */
import { ElMessage } from "element-plus";
import { onMounted } from "vue";
import { useRouter } from "vue-router";

import PaginatedTable from "@/core/components/PaginatedTable.vue";
import { promptText } from "@/core/dialogs";
import { fmtTime } from "@/core/format";
import { showError } from "@/core/http";
import { usePagedList } from "@/core/pagedList";
import { useRooms } from "@/core/rooms";

import { roomApi, type ApplicationForApprover } from "../api";

const router = useRouter();
const { load: loadRooms, nameOf } = useRooms({ is_whole_bookable: true });
const { items, total, page, size, loading, load } = usePagedList((p) =>
  roomApi.GET("/api/v1/room/approvals/todo", { params: { query: p } }).then((r) => r.data!),
);

/** 最后一级通过时占用教室，该时段的座位预约会被取消 */
function approveTip(row: ApplicationForApprover): string {
  const final = row.current_level === row.total_levels;
  if (!final) return `通过第 ${row.current_level} 级审批，进入下一级？（可填审批意见）`;
  const affected = row.affected_reservations > 0 ? `，该时段 ${row.affected_reservations} 条座位预约将被取消` : "";
  return `这是最后一级审批，通过后将占用教室${affected}。（可填审批意见）`;
}

async function act(row: ApplicationForApprover, action: "approve" | "reject") {
  const comment = await promptText(
    action === "approve" ? approveTip(row) : "驳回该申请？（可填驳回原因）",
    action === "approve" ? "通过" : "驳回",
    { inputType: "textarea", maxLength: 500 },
  );
  if (comment === null) return;
  try {
    await roomApi.POST(`/api/v1/room/applications/{application_id}/${action}`, {
      params: { path: { application_id: row.id } },
      body: { comment: comment || null },
    });
    ElMessage.success(action === "approve" ? "已通过" : "已驳回");
    await load();
  } catch (e) {
    showError(e);
  }
}

onMounted(() => {
  void load();
  void loadRooms();
});
</script>

<template>
  <PaginatedTable :data="items" :loading="loading" :total="total" v-model:page="page" v-model:size="size">
    <el-table-column label="申请号" prop="id" width="80" />
    <el-table-column label="申请人" prop="applicant.name" width="100" />
    <el-table-column label="教室" width="160">
      <template #default="{ row }">{{ nameOf(row.room_id) }}</template>
    </el-table-column>
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
