"""权限码目录与预置角色。seed 据此写库；各模块新增权限码时在这里登记。

权限码格式：<模块>:<动作>。服务只按权限码鉴权，角色只是权限码的组合，管理员可以新建角色。
"""

PERMISSIONS: dict[str, tuple[str, str]] = {
    # code: (module, description)
    "admin:user": ("common", "管理用户与用户角色"),
    "admin:role": ("common", "管理角色与权限"),
    "audit:read": ("common", "查询操作审计"),
    "seat:reserve": ("m1", "预约座位、签到、查看自己的预约与违约"),
    "seat:room_manage": ("m1", "登记/注销自习室与座位，维护开放时间与可用性"),
    "seat:stats": ("m1", "查看预约情况与运营统计"),
    "seat:config": ("m1", "修改预约系统参数"),
    "seat:checkin_code": ("m1", "获取教室签到码（教室屏幕）"),
    "room:apply": ("m2", "申请整教室"),
    "room:approve": ("m2", "审批整教室申请"),
    "room:flow_manage": ("m2", "配置审批流与申请参数"),
    "repair:report": ("m3", "上报故障、验收评价"),
    "repair:dispatch": ("m3", "派单"),
    "repair:work": ("m3", "执行维修"),
    "repair:manage": ("m3", "报修配置、接收超时升级、代验收"),
}

BUILTIN_ROLES: dict[str, tuple[str, list[str]]] = {
    # code: (name, perms)
    "student": ("学生", ["seat:reserve", "room:apply", "repair:report"]),
    "teacher": ("教师", ["room:apply", "repair:report"]),
    "room_admin": ("教室管理员", ["seat:room_manage", "seat:checkin_code", "seat:stats"]),
    "ops_admin": ("运营管理员", ["seat:stats"]),
    "dept_approver": ("院系审批人", ["room:approve"]),
    "school_approver": ("学校审批人", ["room:approve"]),
    "repair_dispatcher": ("维修调度员", ["repair:dispatch", "repair:manage"]),
    "repair_worker": ("维修工", ["repair:work"]),
    "checkin_screen": ("签到屏", ["seat:checkin_code"]),
    "sys_admin": ("系统管理员", list(PERMISSIONS)),
}
