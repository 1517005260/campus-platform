<script setup lang="ts">
import { onMounted, ref, watch } from "vue";

import { fmtTime } from "@/core/format";
import { showError } from "@/core/http";
import { useNotificationStore } from "@/core/notifications";

import { commonApi, type NotificationOut } from "../api";

const store = useNotificationStore();
const items = ref<NotificationOut[]>([]);
const total = ref(0);
const page = ref(1);
const size = 20;
const onlyUnread = ref(false);
const loading = ref(false);

async function load() {
  loading.value = true;
  try {
    const { data } = await commonApi.GET("/api/v1/notifications", {
      params: { query: { page: page.value, size, unread: onlyUnread.value ? true : undefined } },
    });
    items.value = data!.items;
    total.value = data!.total;
  } catch (e) {
    showError(e);
  } finally {
    loading.value = false;
  }
}

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

watch(onlyUnread, () => {
  page.value = 1;
  load();
});
onMounted(load);
</script>

<template>
  <div class="toolbar">
    <el-switch v-model="onlyUnread" active-text="只看未读" />
    <el-button :disabled="store.unread === 0" @click="markAll">全部标为已读</el-button>
  </div>
  <el-table :data="items" v-loading="loading" empty-text="暂无通知" @row-click="markRead">
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
  </el-table>
  <el-pagination
    v-model:current-page="page"
    class="pager"
    layout="total, prev, pager, next"
    :page-size="size"
    :total="total"
    @current-change="load"
  />
</template>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
}
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
</style>
