<script setup lang="ts">
/** 我的申请：资格提示、列表、查看详情、撤回审批中的申请或取消已通过且未开始的申请。 */
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import PaginatedTable from "@/core/components/PaginatedTable.vue";
import { fmtTime } from "@/core/format";
import { showError } from "@/core/http";
import { usePagedList } from "@/core/pagedList";
import { useRooms } from "@/core/rooms";

import { applicationStatusLabel, roomApi, type Application, type Eligibility } from "../api";
import { withdrawAction, withdrawApplication } from "../withdraw";

const router = useRouter();
const eligible = ref<Eligibility | null>(null);
const { load: loadRooms, nameOf } = useRooms({ is_whole_bookable: true });
const { items, total, page, size, loading, load } = usePagedList((p) =>
  roomApi.GET("/api/v1/room/applications/mine", { params: { query: p } }).then((r) => r.data!),
);

async function withdraw(a: Application) {
  if (await withdrawApplication(a)) await load();
}

onMounted(async () => {
  void load();
  void loadRooms();
  try {
    const { data } = await roomApi.GET("/api/v1/room/eligibility");
    eligible.value = data!;
  } catch (e) {
    showError(e);
  }
});
</script>

<template>
  <el-alert
    v-if="eligible && !eligible.eligible"
    type="warning"
    :title="`当前不能申请：${eligible.reasons.join('；')}`"
    :closable="false"
    style="margin-bottom: 12px"
  />

  <div style="margin-bottom: 12px">
    <el-button type="primary" @click="router.push('/room/apply')">提交新申请</el-button>
  </div>

  <PaginatedTable :data="items" :loading="loading" :total="total" v-model:page="page" v-model:size="size">
    <el-table-column label="申请号" prop="id" width="80" />
    <el-table-column label="教室" width="160">
      <template #default="{ row }">{{ nameOf(row.room_id) }}</template>
    </el-table-column>
    <el-table-column label="开始">
      <template #default="{ row }">{{ fmtTime(row.start_at) }}</template>
    </el-table-column>
    <el-table-column label="结束">
      <template #default="{ row }">{{ fmtTime(row.end_at) }}</template>
    </el-table-column>
    <el-table-column label="用途" prop="purpose" show-overflow-tooltip />
    <el-table-column label="状态" width="100">
      <template #default="{ row }">
        {{ applicationStatusLabel[row.status as Application["status"]] ?? row.status }}
      </template>
    </el-table-column>
    <el-table-column label="进度" width="70">
      <template #default="{ row }">{{ row.current_level }}/{{ row.total_levels }}</template>
    </el-table-column>
    <el-table-column label="操作" width="130">
      <template #default="{ row }">
        <el-button size="small" link type="primary" @click="router.push(`/room/applications/${row.id}`)">
          详情
        </el-button>
        <el-button v-if="withdrawAction(row)" size="small" link type="danger" @click="withdraw(row)">
          {{ withdrawAction(row)!.label }}
        </el-button>
      </template>
    </el-table-column>
  </PaginatedTable>
</template>
