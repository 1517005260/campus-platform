/**
 * 教室（M1 主数据）的下拉选项、名称与座位编号显示、可选整点，供 M1、M2、M3 页面共用。
 * 教室列表接口分页，这里逐页取完，避免只取第一页时教室多了被截断。
 */
import { computed, reactive, ref } from "vue";

import type { components, paths } from "@/api/types/m1-seat";
import { bizNow, weekdayOf } from "@/core/format";
import { showError } from "@/core/http";
import { seatApi } from "@/core/seatApi";

export type Room = components["schemas"]["Room"];
export type RoomDetail = components["schemas"]["RoomDetail"];
export type OpenHour = components["schemas"]["OpenHour"];
export type Seat = components["schemas"]["Seat"];
export type RoomQuery = Omit<NonNullable<paths["/api/v1/seat/rooms"]["get"]["parameters"]["query"]>, "page" | "size">;

/** 分页接口允许的最大每页条数（campus_common.pagination） */
const MAX_PAGE_SIZE = 100;

export async function fetchAllRooms(query: RoomQuery = {}): Promise<Room[]> {
  const rooms: Room[] = [];
  for (let page = 1; ; page++) {
    const { data } = await seatApi.GET("/api/v1/seat/rooms", {
      params: { query: { ...query, page, size: MAX_PAGE_SIZE } },
    });
    rooms.push(...data!.items);
    if (data!.items.length < MAX_PAGE_SIZE || rooms.length >= data!.total) return rooms;
  }
}

export function roomLabel(room: Room): string {
  return `${room.building} ${room.name}`;
}

/**
 * 页面里的教室列表：load() 加载（失败时提示并保持原列表），nameOf(id) 显示名称，
 * 当前用户看不到的教室（如其他院系的）显示为 #id。
 */
export function useRooms(query: RoomQuery = {}) {
  const rooms = ref<Room[]>([]);
  const byId = computed(() => new Map(rooms.value.map((r) => [r.id, r])));

  async function load() {
    try {
      rooms.value = await fetchAllRooms(query);
    } catch (e) {
      showError(e);
    }
  }

  function nameOf(id: number): string {
    const room = byId.value.get(id);
    return room ? roomLabel(room) : `#${id}`;
  }

  return { rooms, byId, load, nameOf };
}

/** 教室详情（含座位）按教室缓存，整个会话里每个教室只请求一次；请求失败后下次调用重新请求。 */
const roomDetails = reactive(new Map<number, RoomDetail>());
const detailRequests = new Map<number, Promise<RoomDetail>>();

export function fetchRoomDetail(roomId: number): Promise<RoomDetail> {
  let request = detailRequests.get(roomId);
  if (!request) {
    request = seatApi
      .GET("/api/v1/seat/rooms/{room_id}", { params: { path: { room_id: roomId } } })
      .then(({ data }) => {
        roomDetails.set(roomId, data!);
        return data!;
      });
    request.catch(() => detailRequests.delete(roomId));
    detailRequests.set(roomId, request);
  }
  return request;
}

/**
 * 座位编号（如 A-05），可以直接在模板里调用：首次用到某个教室时加载它的详情，加载完成后自动刷新显示；
 * 加载中、教室对当前用户不可见或请求失败时显示为 #id。
 */
export function seatCode(roomId: number, seatId: number): string {
  fetchRoomDetail(roomId).catch(() => {});
  return roomDetails.get(roomId)?.seats.find((s) => s.id === seatId)?.code ?? `#${seatId}`;
}

/** 未给出教室开放时间时使用的默认整点范围（搜索座位等不针对具体教室的场景） */
export const DEFAULT_OPEN_HOURS = { open: 8, close: 22 } as const;

/** 教室在某天（YYYY-MM-DD）的开放整点 [open, close)；当天没有配置开放时间时返回 null。 */
export function openHoursOn(openHours: OpenHour[], date: string): { open: number; close: number } | null {
  const row = openHours.find((h) => h.weekday === weekdayOf(date));
  return row ? { open: row.open_hour, close: row.close_hour } : null;
}

/**
 * 某天可以预约的整点范围 [open, close)：按教室当天的开放时间（未给出开放时间时用默认范围）；
 * 当天已经开始的整点不可选（与后端 RESERVATION_IN_PAST 一致）。当天不开放或已没有可选整点时返回 null。
 */
export function bookableHours(
  openHours: OpenHour[] | undefined,
  date: string,
  now = bizNow(),
): { open: number; close: number } | null {
  const hours = openHours?.length ? openHoursOn(openHours, date) : DEFAULT_OPEN_HOURS;
  if (!hours) return null;
  const open = date === now.date ? Math.max(hours.open, now.hour + 1) : hours.open;
  return open < hours.close ? { open, close: hours.close } : null;
}
