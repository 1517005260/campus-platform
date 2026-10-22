<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { authApi } from "@/core/auth/api";
import { useAuthStore } from "@/core/auth/store";
import { showError } from "@/core/http";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const form = ref({ username: "", password: "" });
const loading = ref(false);

async function submit() {
  loading.value = true;
  try {
    const { data } = await authApi.POST("/api/v1/auth/login", { body: form.value });
    auth.login(data!.access_token, data!.user);
    router.replace((route.query.redirect as string) || "/");
  } catch (e) {
    showError(e);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <el-card class="login-card">
      <h1>校园资源服务平台</h1>
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="用户名">
          <el-input v-model="form.username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" autocomplete="current-password" show-password />
        </el-form-item>
        <el-button type="primary" native-type="submit" :loading="loading" style="width: 100%">登录</el-button>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: var(--el-fill-color-light);
}
.login-card {
  width: 360px;
}
h1 {
  font-size: 20px;
  margin: 0 0 16px;
  text-align: center;
}
</style>
