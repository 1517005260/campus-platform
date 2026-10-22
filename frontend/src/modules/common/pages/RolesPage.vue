<script setup lang="ts">
import { onMounted, ref } from "vue";

import { showError } from "@/core/http";

import { commonApi, type PermissionOut, type RoleOut } from "../api";

const roles = ref<RoleOut[]>([]);
const perms = ref<PermissionOut[]>([]);

onMounted(async () => {
  try {
    const [r, p] = await Promise.all([
      commonApi.GET("/api/v1/admin/roles"),
      commonApi.GET("/api/v1/admin/permissions"),
    ]);
    roles.value = r.data!;
    perms.value = p.data!;
  } catch (e) {
    showError(e);
  }
});
</script>

<template>
  <el-row :gutter="16">
    <el-col :span="14">
      <el-card header="角色">
        <el-table :data="roles" size="small">
          <el-table-column label="编码" prop="code" width="150" />
          <el-table-column label="名称" prop="name" width="120" />
          <el-table-column label="权限">
            <template #default="{ row }">
              <el-tag v-for="p in row.perms" :key="p" size="small" style="margin: 2px">{{ p }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </el-col>
    <el-col :span="10">
      <el-card header="权限码目录">
        <el-table :data="perms" size="small">
          <el-table-column label="编码" prop="code" width="160" />
          <el-table-column label="模块" prop="module" width="80" />
          <el-table-column label="说明" prop="description" />
        </el-table>
      </el-card>
    </el-col>
  </el-row>
</template>
