<script setup lang="ts">
import { onMounted, ref, watch } from "vue";

import PaginatedTable from "@/core/components/PaginatedTable.vue";
import { fmtTime } from "@/core/format";
import { showError } from "@/core/http";
import { useNotificationStore } from "@/core/notifications";
import { usePagedList } from "@/core/pagedList";

import { commonApi, type NotificationOut } from "../api";

const store = useNotificationStore();
const onlyUnread = ref(false);
const { items, total, page, size, loading, load, reload } = usePagedList((p) =>
  commonApi
    .GET("/api/v1/notifications", { params: { query: { unread: onlyUnread.value || undefined, ...p } } })
    .then((r) => r.data!),
);

async function markRead(n: NotificationOut) {
  if (n.read_at) return;
  try {
    await commonApi.POST("/api/v1/notifications/{notification_id}/read", {
      params: { path: { notification_id: n.id } },
    });
    await Promise.all([load(), store.refresh()]);
  } catch (e) {
    showError(e);
  }
}

async function markAll() {
  try {
    await commonApi.POST("/api/v1/notifications/read-all");
    await Promise.all([load(), store.refresh()]);
  } catch (e) {
    showError(e);
  }
}

watch(onlyUnread, reload);
onMounted(load);
</script>

<template>
  <div class="toolbar">
    <el-switch v-model="onlyUnread" active-text="只看未读" />
    <el-button :disabled="store.unread === 0" @click="markAll">全部标为已读</el-button>
  </div>
  <PaginatedTable
    :data="items"
    :loading="loading"
    :total="total"
    v-model:page="page"
    v-model:size="size"
    empty-text="暂无通知"
    @row-click="markRead"
  >
    <el-table-column width="70">
      <template #default="{ row }">
        <el-tag v-if="!row.read_at" size="small" type="danger">未读</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="标题" prop="title" width="220" />
    <el-table-column label="内容" prop="content" />
    <el-table-column label="时间" width="180">
      <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
    </el-table-column>
    <el-table-column width="110">
      <template #default="{ row }">
        <el-button v-if="!row.read_at" size="small" link type="primary" @click.stop="markRead(row)">
          标为已读
        </el-button>
      </template>
    </el-table-column>
  </PaginatedTable>
</template>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
}
</style>
