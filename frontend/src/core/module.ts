/**
 * 模块清单。每个模块在 src/modules/<模块>/index.ts 里导出一个 AppModule，
 * 声明自己的路由和菜单；core 负责合并路由、按权限过滤菜单。
 *
 * 路由的 meta.perms 是访问该页面需要的权限码（任一满足）；不写表示只要求登录。
 */
import type { RouteRecordRaw } from "vue-router";

export interface MenuItem {
  title: string;
  /** 路由路径，例如 /seat/search */
  path: string;
  /** 需要的权限码，任一满足即显示；不写表示登录即可见 */
  perms?: string[];
}

export interface AppModule {
  /** 与后端服务目录同名：common / m1-seat / m2-room / m3-repair */
  id: string;
  /** 菜单分组标题 */
  title: string;
  routes: RouteRecordRaw[];
  menu: MenuItem[];
}

declare module "vue-router" {
  interface RouteMeta {
    title?: string;
    perms?: string[];
  }
}
