/** 登录状态：token 与当前用户。token 存 localStorage，刷新页面后仍然登录。 */
import { defineStore } from "pinia";
import { computed, ref } from "vue";

import type { components } from "@/api/types/common";

export type CurrentUser = components["schemas"]["CurrentUser"];

const TOKEN_KEY = "campus.token";
const USER_KEY = "campus.user";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY));
  const user = ref<CurrentUser | null>(JSON.parse(localStorage.getItem(USER_KEY) ?? "null"));

  const isLoggedIn = computed(() => token.value !== null);
  const perms = computed(() => new Set(user.value?.perms ?? []));

  /** 拥有任一权限码即为 true；不传参数表示只要求登录。 */
  function can(...required: string[]): boolean {
    if (!isLoggedIn.value) return false;
    return required.length === 0 || required.some((p) => perms.value.has(p));
  }

  function login(newToken: string, newUser: CurrentUser) {
    token.value = newToken;
    user.value = newUser;
    localStorage.setItem(TOKEN_KEY, newToken);
    localStorage.setItem(USER_KEY, JSON.stringify(newUser));
  }

  function logout() {
    token.value = null;
    user.value = null;
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    if (location.pathname !== "/login") location.href = `/login?redirect=${encodeURIComponent(location.pathname)}`;
  }

  return { token, user, isLoggedIn, can, login, logout };
});
