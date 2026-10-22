<script setup lang="ts">
import { onMounted, ref } from "vue";

import { useAuthStore } from "@/core/auth/store";

interface VersionInfo {
  service: string;
  version: string;
  git_sha: string;
  env: string;
}

const auth = useAuthStore();
const versions = ref<VersionInfo[]>([]);

onMounted(async () => {
  const results = await Promise.allSettled(
    ["common", "m1", "m2", "m3"].map((s) => fetch(`/ops/${s}/version`).then((r) => r.json())),
  );
  versions.value = results.filter((r) => r.status === "fulfilled").map((r) => r.value as VersionInfo);
});
</script>

<template>
  <el-card header="当前用户">
    <p>{{ auth.user?.name }}（{{ auth.user?.username }}），权限：</p>
    <el-tag v-for="p in auth.user?.perms" :key="p" size="small" type="info" style="margin: 2px">{{ p }}</el-tag>
  </el-card>
  <el-card header="服务版本" style="margin-top: 16px">
    <el-table :data="versions" size="small">
      <el-table-column prop="service" label="服务" />
      <el-table-column prop="version" label="版本" />
      <el-table-column label="提交">
        <template #default="{ row }">{{ row.git_sha.slice(0, 7) }}</template>
      </el-table-column>
      <el-table-column prop="env" label="环境" />
    </el-table>
  </el-card>
</template>
