/**
 * 站内通知未读数，供顶栏铃铛与"我的通知"页面共享：页面标记已读后调用 refresh()，铃铛立即更新。
 * 通知由各模块经消息发给 common，因此放在 core 而不是某个业务模块。
 */
import { defineStore } from "pinia";
import { ref } from "vue";

import { commonApi } from "@/core/commonApi";

export const useNotificationStore = defineStore("notifications", () => {
  const unread = ref(0);

  async function refresh() {
    try {
      const { data } = await commonApi.GET("/api/v1/notifications/unread-count");
      unread.value = data!.count;
    } catch {
      // 铃铛只是提示；失败（含 401 已由 http 层处理）时保持上一次的数字，不打扰用户
    }
  }

  return { unread, refresh };
});
