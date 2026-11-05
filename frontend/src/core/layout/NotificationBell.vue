<script setup lang="ts">
import { Bell } from "@element-plus/icons-vue";
import { onMounted, onUnmounted, watch } from "vue";
import { useRoute } from "vue-router";

import { useNotificationStore } from "@/core/notifications";

/** 未读数每分钟刷新一次，切换页面时也刷新；点击进入"我的通知"。 */
const POLL_MS = 60_000;

const store = useNotificationStore();
const route = useRoute();
let timer: ReturnType<typeof setInterval> | undefined;

onMounted(() => {
  store.refresh();
  timer = setInterval(store.refresh, POLL_MS);
});
onUnmounted(() => clearInterval(timer));
watch(() => route.path, store.refresh);
</script>

<template>
  <router-link to="/notifications" class="bell" title="我的通知">
    <el-badge :value="store.unread" :hidden="store.unread === 0" :max="99">
      <el-icon :size="20"><Bell /></el-icon>
    </el-badge>
  </router-link>
</template>

<style scoped>
.bell {
  display: inline-flex;
  align-items: center;
  margin-right: 16px;
  color: var(--el-text-color-regular);
}
</style>
