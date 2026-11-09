// 由 scripts/gen-types.mjs 从 contracts/openapi/m1-seat.json 生成，不要手改。
export interface paths {
    "/api/v1/seat/reservations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 预约座位
         * @description 校验与座位搜索使用同一组规则。错误：
         *     422 `VALIDATION_ERROR`（结束不晚于开始）；
         *     400 `RESERVATION_IN_PAST`、`INVALID_DURATION`（超过 `max_hours`）、`OUTSIDE_OPEN_HOURS`；
         *     404 `NOT_FOUND`（座位不存在）；403 `DEPT_RESTRICTED`；
         *     409 `SEAT_NOT_AVAILABLE`（座位或教室停用、被预约、被 M2/M3 占用）、`USER_TIME_CONFLICT`。
         */
        post: operations["create_reservation_api_v1_seat_reservations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/seat/reservations/{reservation_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 取消预约
         * @description 只能取消自己未开始的 booked 预约。不是本人的预约：404 `NOT_FOUND`；其他状态或已开始：
         *     409 `RESERVATION_STATE_CONFLICT`。
         */
        post: operations["cancel_reservation_api_v1_seat_reservations__reservation_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/seat/reservations/{reservation_id}/check-in": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 签到
         * @description 签到窗口：开始前 15 分钟至开始后 `auto_cancel_min` 分钟之前；签到码为教室屏幕当前显示的当天的码。
         *
         *     错误：404 `NOT_FOUND`（不是本人的预约）；409 `RESERVATION_STATE_CONFLICT`（不是 booked，包括已被取消）；
         *     400 `CHECKIN_WINDOW_CLOSED`、`CHECKIN_CODE_INVALID`。
         */
        post: operations["check_in_api_v1_seat_reservations__reservation_id__check_in_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/seat/reservations/{reservation_id}/rebook": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 按历史预约再次预约同一座位
         * @description 为历史预约的同一座位预约新时段。历史预约不是本人的：404 `NOT_FOUND`；其余错误同"预约座位"。
         */
        post: operations["rebook_api_v1_seat_reservations__reservation_id__rebook_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/seat/reservations/mine": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 我的预约历史 */
        get: operations["my_reservations_api_v1_seat_reservations_mine_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/seat/rooms": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 查询自习室列表
         * @description 院系自习室只对本院系用户可见（按 token 中的 dept_id 过滤）；
         *     `seat:checkin_code` 可见所有院系的启用教室；`seat:room_manage`、`seat:stats` 可见全部教室（含停用）。
         *     详情、可用性的可见性相同。
         */
        get: operations["list_rooms_api_v1_seat_rooms_get"];
        put?: never;
        /**
         * 登记自习室
         * @description 同一星期配置多条开放时间：400 `INVALID_OPEN_HOURS`；同一楼宇重名：409 `ROOM_ALREADY_EXISTS`。
         */
        post: operations["create_room_api_v1_seat_rooms_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/seat/rooms/{room_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 自习室详情（含座位）
         * @description 教室不存在或对当前用户不可见：404 `NOT_FOUND`。
         */
        get: operations["get_room_api_v1_seat_rooms__room_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * 修改自习室（含开放时间、启用/停用）
         * @description 停用教室或注销自习室（`is_study_room` 由 true 改为 false）时，该教室尚未结束的有效预约全部取消
         *     （`cancel_reason=ADMIN_DISABLED`，不记违约，通知学生）。
         *
         *     错误：404 `NOT_FOUND`；400 `INVALID_OPEN_HOURS`；409 `ROOM_ALREADY_EXISTS`。
         */
        patch: operations["update_room_api_v1_seat_rooms__room_id__patch"];
        trace?: never;
    };
    "/api/v1/seat/rooms/{room_id}/availability": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 某天各座位按小时的状态
         * @description 每个座位每个整点：closed（不在开放时间）、
         *     blocked（`M1_ADMIN` 停用或 `M2_OCCUPY`/`M3_MAINTENANCE` 占用）、reserved（有效预约）、free。
         *     教室不存在或不可见：404 `NOT_FOUND`。
         */
        get: operations["room_availability_api_v1_seat_rooms__room_id__availability_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/seat/rooms/{room_id}/checkin-code": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 当日签到码（教室屏幕用）
         * @description 业务日期当天的签到码，当天首次请求时生成。
         *     附签到窗口：预约开始前 `early_minutes` 分钟至开始后 `auto_cancel_min` 分钟（与签到接口同一组参数）。
         *
         *     教室不存在：404 `NOT_FOUND`。
         */
        get: operations["get_checkin_code_api_v1_seat_rooms__room_id__checkin_code_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/seat/rooms/{room_id}/seats": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 登记座位
         * @description 教室不存在：404 `NOT_FOUND`；同一教室座位编号重复：409 `SEAT_ALREADY_EXISTS`。
         */
        post: operations["create_seat_api_v1_seat_rooms__room_id__seats_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/seat/seats/{seat_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * 修改座位（插座标记、启用/停用）
         * @description 停用座位时，该座位尚未结束的有效预约全部取消（`cancel_reason=ADMIN_DISABLED`，不记违约，通知学生）。
         *
         *     座位不存在：404 `NOT_FOUND`。
         */
        patch: operations["update_seat_api_v1_seat_seats__seat_id__patch"];
        trace?: never;
    };
    "/api/v1/seat/seats/{seat_id}/status-history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 座位状态变化及写入来源
         * @description 座位不存在：404 `NOT_FOUND`。
         */
        get: operations["seat_status_history_api_v1_seat_seats__seat_id__status_history_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/seat/seats/search": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 按条件搜索可预约座位
         * @description 只返回当前用户在该时段真正可约的座位，规则与创建预约相同：座位与教室启用、院系允许、
         *     在开放时间内、无有效预约、无 M2/M3 占用。
         *
         *     时段本身不可约时与创建预约返回同样的错误：结束不晚于开始 422 `VALIDATION_ERROR`；
         *     时段已开始 400 `RESERVATION_IN_PAST`；超过 `max_hours` 400 `INVALID_DURATION`。
         */
        get: operations["search_seats_api_v1_seat_seats_search_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/seat/settings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 查看预约参数 */
        get: operations["get_settings_api_v1_seat_settings_get"];
        /**
         * 修改预约参数
         * @description `remind_late_min` 必须小于 `auto_cancel_min`，否则 422 `VALIDATION_ERROR`。
         */
        put: operations["put_settings_api_v1_seat_settings_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/seat/stats/usage": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 座位利用率与违约率
         * @description 利用率与违约率口径见 ADR-012。
         *
         *     `date_to` 早于 `date_from`：400 `INVALID_DATE_RANGE`；教室不存在：404 `NOT_FOUND`。
         */
        get: operations["usage_stats_api_v1_seat_stats_usage_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/seat/violations/mine": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 我的违约记录 */
        get: operations["my_violations_api_v1_seat_violations_mine_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 存活检查 */
        get: operations["health_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/blocks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 占用或下架整间教室
         * @description 在 [start_at, end_at) 内下架该教室全部座位，并记录写入来源 (source, ref_id)。
         *
         *     时段内已有的个人预约自动取消（cancel_reason=BLOCKED_BY_M2/M3）、通知学生、不记违约，
         *     在返回值中列出。
         *
         *     先按幂等键处理：同一幂等键 + 同样的请求，无论占用后来是否已释放，都原样重放首次结果（200）；
         *     同一幂等键 + 不同的请求返回 409 `IDEMPOTENCY_KEY_REUSED`。M2、M3 的键按单号固定
         *     （`m2-app-{id}-occupy`、`m3-order-{id}-block`），因此它们重发同一单号只会走到这一步。
         *     换了幂等键时再按 (source, ref_id) 处理：一个单号只对应一次占用，已释放返回 409 `BLOCK_ALREADY_RELEASED`，
         *     请求不同返回 409 `BLOCK_REFERENCE_CONFLICT`，相同则返回已有的 block_id 且不再取消预约。
         *
         *     M2 的新占用与该教室未释放的 M3 维修下架时段重叠（维修下架 end_at 为空，即从维修开始起无限期）时
         *     返回 409 `ROOM_UNDER_MAINTENANCE`；反过来 M3 下架不受 M2 占用限制（紧急维修优先），照常取消时段内的预约。
         *
         *     其他错误：403 `BLOCK_SOURCE_FORBIDDEN`（source 与调用方不符）；404 `NOT_FOUND`（教室不存在）；
         *     422 `VALIDATION_ERROR`（end_at 不晚于 start_at）。
         */
        post: operations["create_block_internal_v1_blocks_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/blocks/{source}/{ref_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * 释放占用
         * @description M2 撤销/超时、M3 验收通过时调用。幂等：不存在或已释放时返回 released=false。
         *
         *     source 与调用方不符：403 `BLOCK_SOURCE_FORBIDDEN`。
         */
        delete: operations["release_block_internal_v1_blocks__source___ref_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/rooms/{room_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 查询教室（含座位）
         * @description 不论启用状态与院系，返回教室及其全部座位（含停用的座位，M3 上报故障时用来校验座位归属）。
         *
         *     教室不存在：404 `NOT_FOUND`。
         */
        get: operations["internal_get_room_internal_v1_rooms__room_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/rooms/{room_id}/reservations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 查询时段内的有效个人预约
         * @description M2 审批人审批前查看"批准后会影响多少人"。
         *
         *     教室不存在：404 `NOT_FOUND`；end_at 不晚于 start_at：422 `VALIDATION_ERROR`。
         */
        get: operations["room_reservations_internal_v1_rooms__room_id__reservations_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/users/{user_id}/violations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 用户违约次数
         * @description 统计 created_at >= since 的违约次数（含 since 时刻）。
         *
         *     只允许 M2 调用，其他服务：403 `SERVICE_FORBIDDEN`。
         */
        get: operations["violation_count_internal_v1_users__user_id__violations_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 就绪检查：数据库可用 */
        get: operations["ready_ready_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/version": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 当前运行版本 */
        get: operations["version_version_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** CheckinCodeOut */
        CheckinCodeOut: {
            /**
             * Auto Cancel Min
             * @description 签到窗口：预约开始后多少分钟内可签到，之后自动取消并记违约
             */
            auto_cancel_min: number;
            /** Code */
            code: string;
            /**
             * Early Minutes
             * @description 签到窗口：预约开始前多少分钟起可签到
             */
            early_minutes: number;
            /**
             * Qr Payload
             * @description 二维码内容，微信扫码签到用
             */
            qr_payload: string;
            /** Room Id */
            room_id: number;
            /**
             * Valid Date
             * Format: date
             */
            valid_date: string;
        };
        /** CheckInRequest */
        CheckInRequest: {
            /**
             * Code
             * @description 教室屏幕上显示的签到码
             */
            code: string;
        };
        /** ErrorBody */
        ErrorBody: {
            /** Code */
            code: string;
            /** Details */
            details?: unknown;
            /** Message */
            message: string;
            /** Request Id */
            request_id?: string | null;
        };
        /**
         * HourRange
         * @description 整点时段（业务时区），预约、复订的请求体，也是座位搜索的查询参数。结束不晚于开始时返回 422。
         */
        HourRange: {
            /**
             * Date
             * Format: date
             */
            date: string;
            /**
             * End Hour
             * @description 结束整点（不含）
             */
            end_hour: number;
            /**
             * Start Hour
             * @description 开始整点
             */
            start_hour: number;
        };
        /** HourState */
        HourState: {
            /** Hour */
            hour: number;
            /** Source */
            source?: ("M1_RESERVATION" | "M1_ADMIN" | "M2_OCCUPY" | "M3_MAINTENANCE") | null;
            /**
             * State
             * @enum {string}
             */
            state: "free" | "reserved" | "blocked" | "closed";
        };
        /** InternalBlockCreate */
        InternalBlockCreate: {
            /**
             * End At
             * @description 为空表示结束时间未知（维修中）
             */
            end_at?: string | null;
            /** Reason */
            reason: string;
            /**
             * Ref Id
             * @description M2 申请 ID 或 M3 工单 ID
             */
            ref_id: number;
            /** Room Id */
            room_id: number;
            /**
             * Source
             * @enum {string}
             */
            source: "M2_OCCUPY" | "M3_MAINTENANCE";
            /**
             * Start At
             * Format: date-time
             */
            start_at: string;
        };
        /** InternalBlockResult */
        InternalBlockResult: {
            /** Block Id */
            block_id: number;
            /**
             * Cancelled Reservations
             * @description 因本次占用被取消的个人预约（已通知学生，不记违约）
             */
            cancelled_reservations: components["schemas"]["Reservation"][];
        };
        /** InternalReleaseResult */
        InternalReleaseResult: {
            /**
             * Released
             * @description false 表示本来就没有该占用，重复调用也不报错
             */
            released: boolean;
        };
        /** InternalViolationCount */
        InternalViolationCount: {
            /** Count */
            count: number;
            /** User Id */
            user_id: number;
        };
        /** OpenHour */
        OpenHour: {
            /** Close Hour */
            close_hour: number;
            /** Open Hour */
            open_hour: number;
            /**
             * Weekday
             * @description 0 = 周一
             */
            weekday: number;
        };
        /** Page[ReservationDetail] */
        Page_ReservationDetail_: {
            /** Items */
            items: components["schemas"]["ReservationDetail"][];
            /** Page */
            page: number;
            /** Size */
            size: number;
            /** Total */
            total: number;
        };
        /** Page[Room] */
        Page_Room_: {
            /** Items */
            items: components["schemas"]["Room"][];
            /** Page */
            page: number;
            /** Size */
            size: number;
            /** Total */
            total: number;
        };
        /** Page[SeatSearchItem] */
        Page_SeatSearchItem_: {
            /** Items */
            items: components["schemas"]["SeatSearchItem"][];
            /** Page */
            page: number;
            /** Size */
            size: number;
            /** Total */
            total: number;
        };
        /** Page[ViolationOut] */
        Page_ViolationOut_: {
            /** Items */
            items: components["schemas"]["ViolationOut"][];
            /** Page */
            page: number;
            /** Size */
            size: number;
            /** Total */
            total: number;
        };
        /** Reservation */
        Reservation: {
            /** Cancel Reason */
            cancel_reason?: string | null;
            /** Checked In At */
            checked_in_at?: string | null;
            /**
             * End At
             * Format: date-time
             */
            end_at: string;
            /** Id */
            id: number;
            /** Room Id */
            room_id: number;
            /** Seat Id */
            seat_id: number;
            /**
             * Start At
             * Format: date-time
             */
            start_at: string;
            /**
             * Status
             * @enum {string}
             */
            status: "booked" | "checked_in" | "completed" | "cancelled" | "no_show";
            /** User Id */
            user_id: number;
        };
        /** ReservationCreate */
        ReservationCreate: {
            /**
             * Date
             * Format: date
             */
            date: string;
            /**
             * End Hour
             * @description 结束整点（不含）
             */
            end_hour: number;
            /** Seat Id */
            seat_id: number;
            /**
             * Start Hour
             * @description 开始整点
             */
            start_hour: number;
        };
        /** ReservationDetail */
        ReservationDetail: {
            /** Cancel Reason */
            cancel_reason?: string | null;
            /** Checked In At */
            checked_in_at?: string | null;
            /**
             * End At
             * Format: date-time
             */
            end_at: string;
            /** Id */
            id: number;
            room: components["schemas"]["Room"];
            /** Room Id */
            room_id: number;
            seat: components["schemas"]["Seat"];
            /** Seat Id */
            seat_id: number;
            /**
             * Start At
             * Format: date-time
             */
            start_at: string;
            /**
             * Status
             * @enum {string}
             */
            status: "booked" | "checked_in" | "completed" | "cancelled" | "no_show";
            /** User Id */
            user_id: number;
        };
        /** Room */
        Room: {
            /**
             * Building
             * @example 第三教学楼
             */
            building: string;
            /** Capacity */
            capacity: number;
            /**
             * Dept Id
             * @description 为空表示全校开放；否则只对本院系开放
             */
            dept_id?: number | null;
            /** Floor */
            floor: number;
            /** Id */
            id: number;
            /**
             * Is Study Room
             * @default true
             */
            is_study_room: boolean;
            /**
             * Is Whole Bookable
             * @description 是否允许 M2 整教室申请
             * @default false
             */
            is_whole_bookable: boolean;
            /**
             * Name
             * @example H3106
             */
            name: string;
            /**
             * Open Hours
             * @default []
             */
            open_hours: components["schemas"]["OpenHour"][];
            /**
             * Status
             * @enum {string}
             */
            status: "enabled" | "disabled";
            /**
             * Type
             * @enum {string}
             */
            type: "classroom" | "library" | "other";
        };
        /** RoomCreate */
        RoomCreate: {
            /**
             * Building
             * @example 第三教学楼
             */
            building: string;
            /** Capacity */
            capacity: number;
            /**
             * Dept Id
             * @description 为空表示全校开放；否则只对本院系开放
             */
            dept_id?: number | null;
            /** Floor */
            floor: number;
            /**
             * Is Study Room
             * @default true
             */
            is_study_room: boolean;
            /**
             * Is Whole Bookable
             * @description 是否允许 M2 整教室申请
             * @default false
             */
            is_whole_bookable: boolean;
            /**
             * Name
             * @example H3106
             */
            name: string;
            /**
             * Open Hours
             * @default []
             */
            open_hours: components["schemas"]["OpenHour"][];
            /**
             * Type
             * @enum {string}
             */
            type: "classroom" | "library" | "other";
        };
        /** RoomDetail */
        RoomDetail: {
            /**
             * Building
             * @example 第三教学楼
             */
            building: string;
            /** Capacity */
            capacity: number;
            /**
             * Dept Id
             * @description 为空表示全校开放；否则只对本院系开放
             */
            dept_id?: number | null;
            /** Floor */
            floor: number;
            /** Id */
            id: number;
            /**
             * Is Study Room
             * @default true
             */
            is_study_room: boolean;
            /**
             * Is Whole Bookable
             * @description 是否允许 M2 整教室申请
             * @default false
             */
            is_whole_bookable: boolean;
            /**
             * Name
             * @example H3106
             */
            name: string;
            /**
             * Open Hours
             * @default []
             */
            open_hours: components["schemas"]["OpenHour"][];
            /** Seats */
            seats: components["schemas"]["Seat"][];
            /**
             * Status
             * @enum {string}
             */
            status: "enabled" | "disabled";
            /**
             * Type
             * @enum {string}
             */
            type: "classroom" | "library" | "other";
        };
        /** RoomUpdate */
        RoomUpdate: {
            /** Building */
            building?: string;
            /** Capacity */
            capacity?: number;
            /**
             * Dept Id
             * @description null 表示改为全校开放
             */
            dept_id?: number | null;
            /** Floor */
            floor?: number;
            /**
             * Is Study Room
             * @description 改为 false 即注销自习室，尚未结束的有效预约被取消
             */
            is_study_room?: boolean;
            /** Is Whole Bookable */
            is_whole_bookable?: boolean;
            /** Name */
            name?: string;
            /** Open Hours */
            open_hours?: components["schemas"]["OpenHour"][];
            /**
             * Status
             * @enum {string}
             */
            status?: "enabled" | "disabled";
            /**
             * Type
             * @enum {string}
             */
            type?: "classroom" | "library" | "other";
        };
        /** RoomUsage */
        RoomUsage: {
            /** No Show Rate */
            no_show_rate: number;
            /** Reservations */
            reservations: number;
            /** Room Id */
            room_id: number;
            /** Utilization */
            utilization: number;
        };
        /** Seat */
        Seat: {
            /** Code */
            code: string;
            /** Id */
            id: number;
            /**
             * Outlet
             * @description none 无插座；fixed 靠近固定插座；rail 靠近移动导轨插座
             * @enum {string}
             */
            outlet: "none" | "fixed" | "rail";
            /** Room Id */
            room_id: number;
            /**
             * Status
             * @enum {string}
             */
            status: "enabled" | "disabled";
        };
        /** SeatAvailability */
        SeatAvailability: {
            /** Hours */
            hours: components["schemas"]["HourState"][];
            /** Seat Id */
            seat_id: number;
        };
        /** SeatCreate */
        SeatCreate: {
            /**
             * Code
             * @example A-01
             */
            code: string;
            /**
             * Outlet
             * @default none
             * @enum {string}
             */
            outlet: "none" | "fixed" | "rail";
        };
        /** SeatSearchItem */
        SeatSearchItem: {
            room: components["schemas"]["Room"];
            seat: components["schemas"]["Seat"];
        };
        /**
         * SeatSettings
         * @description 可调系统参数，括号内为默认值。
         */
        SeatSettings: {
            /**
             * Auto Cancel Min
             * @description 开始后多少分钟未签到自动取消并记违约
             * @default 15
             */
            auto_cancel_min: number;
            /**
             * Max Hours
             * @description 单次预约最多小时数
             * @default 4
             */
            max_hours: number;
            /**
             * Remind Before Min
             * @description 开始前多少分钟提醒
             * @default 15
             */
            remind_before_min: number;
            /**
             * Remind Late Min
             * @description 开始后多少分钟未签到再次提醒，必须小于 auto_cancel_min
             * @default 10
             */
            remind_late_min: number;
        };
        /**
         * SeatUpdate
         * @description PATCH 模型，规则同 RoomUpdate。
         */
        SeatUpdate: {
            /**
             * Outlet
             * @enum {string}
             */
            outlet?: "none" | "fixed" | "rail";
            /**
             * Status
             * @enum {string}
             */
            status?: "enabled" | "disabled";
        };
        /** StatusHistoryItem */
        StatusHistoryItem: {
            /**
             * At
             * Format: date-time
             */
            at: string;
            /** End At */
            end_at: string | null;
            /** Ref Id */
            ref_id: number;
            /**
             * Source
             * @enum {string}
             */
            source: "M1_RESERVATION" | "M1_ADMIN" | "M2_OCCUPY" | "M3_MAINTENANCE";
            /** Start At */
            start_at: string | null;
            /**
             * State
             * @enum {string}
             */
            state: "reserved" | "released" | "blocked" | "unblocked";
        };
        /** UsageStats */
        UsageStats: {
            /**
             * By Hour
             * @description 各整点的平均利用率
             */
            by_hour: {
                [key: string]: number;
            };
            /** By Room */
            by_room: components["schemas"]["RoomUsage"][];
            /** No Show Rate */
            no_show_rate: number;
            /**
             * Utilization
             * @description 已签到小时数 / 可预约小时数
             */
            utilization: number;
        };
        /** VersionInfo */
        VersionInfo: {
            /** Env */
            env: string;
            /** Git Sha */
            git_sha: string;
            /** Service */
            service: string;
            /** Version */
            version: string;
        };
        /** ViolationOut */
        ViolationOut: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: number;
            /** Reservation Id */
            reservation_id: number;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    create_reservation_api_v1_seat_reservations_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReservationCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Reservation"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    cancel_reservation_api_v1_seat_reservations__reservation_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reservation_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Reservation"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    check_in_api_v1_seat_reservations__reservation_id__check_in_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reservation_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CheckInRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Reservation"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    rebook_api_v1_seat_reservations__reservation_id__rebook_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reservation_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["HourRange"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Reservation"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    my_reservations_api_v1_seat_reservations_mine_get: {
        parameters: {
            query?: {
                /** @description 页码，从 1 开始 */
                page?: number;
                /** @description 每页条数 */
                size?: number;
                status?: ("booked" | "checked_in" | "completed" | "cancelled" | "no_show") | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_ReservationDetail_"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    list_rooms_api_v1_seat_rooms_get: {
        parameters: {
            query?: {
                /** @description 楼宇名称 */
                building?: string | null;
                is_study_room?: boolean | null;
                /** @description M2 申请选教室时传 true */
                is_whole_bookable?: boolean | null;
                /** @description 页码，从 1 开始 */
                page?: number;
                /** @description 每页条数 */
                size?: number;
                type?: ("classroom" | "library" | "other") | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_Room_"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    create_room_api_v1_seat_rooms_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RoomCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Room"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    get_room_api_v1_seat_rooms__room_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                room_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoomDetail"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    update_room_api_v1_seat_rooms__room_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                room_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RoomUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Room"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    room_availability_api_v1_seat_rooms__room_id__availability_get: {
        parameters: {
            query: {
                date: string;
            };
            header?: never;
            path: {
                room_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SeatAvailability"][];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    get_checkin_code_api_v1_seat_rooms__room_id__checkin_code_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                room_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CheckinCodeOut"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    create_seat_api_v1_seat_rooms__room_id__seats_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                room_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SeatCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Seat"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    update_seat_api_v1_seat_seats__seat_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                seat_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SeatUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Seat"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    seat_status_history_api_v1_seat_seats__seat_id__status_history_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                seat_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StatusHistoryItem"][];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    search_seats_api_v1_seat_seats_search_get: {
        parameters: {
            query: {
                building?: string | null;
                date: string;
                end_hour: number;
                /** @description 按插座条件筛选 */
                outlet?: ("none" | "fixed" | "rail") | null;
                /** @description 页码，从 1 开始 */
                page?: number;
                room_id?: number | null;
                /** @description 每页条数 */
                size?: number;
                start_hour: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_SeatSearchItem_"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    get_settings_api_v1_seat_settings_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SeatSettings"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    put_settings_api_v1_seat_settings_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SeatSettings"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SeatSettings"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    usage_stats_api_v1_seat_stats_usage_get: {
        parameters: {
            query: {
                date_from: string;
                date_to: string;
                room_id?: number | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UsageStats"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    my_violations_api_v1_seat_violations_mine_get: {
        parameters: {
            query?: {
                /** @description 页码，从 1 开始 */
                page?: number;
                /** @description 每页条数 */
                size?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_ViolationOut_"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    health_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    };
                };
            };
        };
    };
    create_block_internal_v1_blocks_post: {
        parameters: {
            query?: never;
            header: {
                /** @description 例如 m3-order-7-block */
                "idempotency-key": string;
                "x-service-key"?: string | null;
                "x-service-name"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["InternalBlockCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InternalBlockResult"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    release_block_internal_v1_blocks__source___ref_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "x-service-key"?: string | null;
                "x-service-name"?: string | null;
            };
            path: {
                ref_id: number;
                source: "M2_OCCUPY" | "M3_MAINTENANCE";
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InternalReleaseResult"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    internal_get_room_internal_v1_rooms__room_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-service-key"?: string | null;
                "x-service-name"?: string | null;
            };
            path: {
                room_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoomDetail"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    room_reservations_internal_v1_rooms__room_id__reservations_get: {
        parameters: {
            query: {
                end_at: string;
                start_at: string;
            };
            header?: {
                "x-service-key"?: string | null;
                "x-service-name"?: string | null;
            };
            path: {
                room_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Reservation"][];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    violation_count_internal_v1_users__user_id__violations_get: {
        parameters: {
            query: {
                since: string;
            };
            header?: {
                "x-service-key"?: string | null;
                "x-service-name"?: string | null;
            };
            path: {
                user_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InternalViolationCount"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
            /** @description Bad Gateway */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    ready_ready_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    version_version_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionInfo"];
                };
            };
        };
    };
}
