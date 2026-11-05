<script setup lang="ts">
/** 我的申请：资格提示、列表、查看详情、撤回待审申请、再借一次。 */
import { ElMessage, ElMessageBox } from "element-plus";
import { onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";

import PaginatedTable from "@/core/components/PaginatedTable.vue";
import { fmtTime } from "@/core/format";
import { showError } from "@/core/http";

import { applicationStatusLabel, roomApi, type Application, type Eligibility } from "../api";

const router = useRouter();
const items = ref<Application[]>([]);
const eligible = ref<Eligibility | null>(null);
const loading = ref(false);
const total = ref(0);
const page = ref(1);
const size = ref(10);

async function load() {
  loading.value = true;
  try {
    const { data } = await roomApi.GET("/api/v1/room/applications/mine", {
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

async function withdraw(a: Application) {
  await ElMessageBox.confirm(`撤回申请 #${a.id}？已通过的占用会一并释放。`, "确认");
  try {
    await roomApi.POST("/api/v1/room/applications/{application_id}/withdraw", {
      params: { path: { application_id: a.id } },
    });
    ElMessage.success("已撤回");
    await load();
  } catch (e) {
    showError(e);
  }
}

watch([page, size], () => void load());
onMounted(async () => {
  try {
    const { data } = await roomApi.GET("/api/v1/room/eligibility");
    eligible.value = data!;
  } catch (e) {
    showError(e);
  }
  await load();
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
    <el-table-column label="教室编号" prop="room_id" width="90" />
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
        <el-button v-if="row.status === 'pending'" size="small" link type="danger" @click="withdraw(row)">
          撤回
        </el-button>
      </template>
    </el-table-column>
  </PaginatedTable>
</template>
