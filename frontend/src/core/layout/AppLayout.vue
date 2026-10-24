<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

import { useAuthStore } from "@/core/auth/store";
import { modules } from "@/modules";

const auth = useAuthStore();
const route = useRoute();

/** 只显示当前用户有权限的菜单项；整组都无权限时不显示该组 */
const visibleModules = computed(() =>
  modules
    .map((m) => ({ ...m, menu: m.menu.filter((item) => auth.can(...(item.perms ?? []))) }))
    .filter((m) => m.menu.length > 0),
);
</script>

<template>
  <el-container class="app">
    <el-aside width="220px">
      <div class="brand">校园资源服务平台</div>
      <el-menu :default-active="route.path" router>
        <el-menu-item index="/">首页</el-menu-item>
        <el-sub-menu v-for="m in visibleModules" :key="m.id" :index="m.id">
          <template #title>{{ m.title }}</template>
          <el-menu-item v-for="item in m.menu" :key="item.path" :index="item.path">
            {{ item.title }}
          </el-menu-item>
        </el-sub-menu>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span>{{ route.meta.title }}</span>
        <span>
          {{ auth.user?.name }}
          <el-tag v-for="r in auth.user?.roles" :key="r" size="small" style="margin-left: 4px">{{ r }}</el-tag>
          <el-button link type="primary" style="margin-left: 12px" @click="auth.logout()">退出</el-button>
        </span>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.app {
  min-height: 100vh;
}
.brand {
  padding: 16px;
  font-weight: 600;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--el-border-color-light);
}
</style>
