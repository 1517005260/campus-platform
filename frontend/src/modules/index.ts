/** 模块注册表。新增模块：在对应目录写 index.ts 导出 AppModule，然后加到这里。 */
import type { AppModule } from "@/core/module";

import common from "./common";
import m1Seat from "./m1-seat";
import m2Room from "./m2-room";
import m3Repair from "./m3-repair";

export const modules: AppModule[] = [m1Seat, m2Room, m3Repair, common];
