from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import FileResponse

from .db import get_db, init_db
from .repository import (
    assign_work_order,
    authenticate,
    create_announcement,
    create_repair_request,
    create_session,
    create_user,
    delete_session,
    ensure_default_admin,
    ensure_default_repairmen,
    get_repair_request,
    get_session,
    get_user_by_id,
    get_work_order,
    list_users_by_role,
    list_announcements,
    list_repair_requests,
    list_repair_requests_for_student,
    list_work_orders,
    list_work_orders_for_repairman,
    stats,
    update_work_order_status,
)
from .schemas import (
    AdminCreateUserIn,
    AnnouncementCreateIn,
    AnnouncementOut,
    LoginIn,
    RegisterIn,
    RepairCreateIn,
    RepairOut,
    StatsOut,
    TokenOut,
    UserOut,
    WorkOrderAssignIn,
    WorkOrderOut,
    WorkOrderStatusIn,
)

app = FastAPI(title="宿舍保修管理系统 API", version="0.1.0")

WEB_INDEX_PATH = Path(__file__).resolve().parents[1] / "web" / "index.html"


@app.on_event("startup")
def _startup() -> None:
    init_db()
    with get_db() as conn:
        ensure_default_admin(conn)
        ensure_default_repairmen(conn)


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _row_to_user_out(row) -> UserOut:
    return UserOut(
        id=int(row["id"]),
        username=str(row["username"]),
        role=str(row["role"]),
        dorm_building=row["dorm_building"],
        dorm_room=row["dorm_room"],
        phone=row["phone"],
        created_at=_parse_dt(row["created_at"]),
    )


def _row_to_repair_out(row) -> RepairOut:
    return RepairOut(
        id=int(row["id"]),
        student_id=int(row["student_id"]),
        title=str(row["title"]),
        description=str(row["description"]),
        location_building=str(row["location_building"]),
        location_room=str(row["location_room"]),
        contact_phone=row["contact_phone"],
        status=str(row["status"]),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _row_to_workorder_out(row) -> WorkOrderOut:
    return WorkOrderOut(
        id=int(row["id"]),
        request_id=int(row["request_id"]),
        assigned_to=int(row["assigned_to"]) if row["assigned_to"] is not None else None,
        status=str(row["status"]),
        note=row["note"],
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
        finished_at=_parse_dt(row["finished_at"]) if row["finished_at"] else None,
    )


def _row_to_announcement_out(row) -> AnnouncementOut:
    return AnnouncementOut(
        id=int(row["id"]),
        title=str(row["title"]),
        content=str(row["content"]),
        created_at=_parse_dt(row["created_at"]),
    )


def get_current_user(authorization: Optional[str] = Header(default=None, alias="Authorization")) -> UserOut:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少 Authorization")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization 格式应为 Bearer <token>")
    token = parts[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token 为空")
    with get_db() as conn:
        sess = get_session(conn, token)
        if not sess:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token 无效或已过期")
        user_row = get_user_by_id(conn, sess.user_id)
        if not user_row:
            delete_session(conn, token)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
        return _row_to_user_out(user_row)


def require_role(*roles: str):
    def _dep(user: UserOut = Depends(get_current_user)) -> UserOut:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return user

    return _dep


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/")
def index() -> FileResponse:
    if not WEB_INDEX_PATH.exists():
        raise HTTPException(status_code=500, detail="前端页面未找到")
    return FileResponse(WEB_INDEX_PATH, headers={"Cache-Control": "no-store"})


@app.post("/api/auth/register", response_model=UserOut)
def register(payload: RegisterIn) -> UserOut:
    with get_db() as conn:
        try:
            user_id = create_user(
                conn,
                username=payload.username,
                password=payload.password,
                role="student",
                dorm_building=payload.dorm_building,
                dorm_room=payload.dorm_room,
                phone=payload.phone,
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="用户名已存在")
        except Exception:
            raise HTTPException(status_code=400, detail="参数不合法")
        row = get_user_by_id(conn, user_id)
        return _row_to_user_out(row)


@app.post("/api/auth/login", response_model=TokenOut)
def login(payload: LoginIn) -> TokenOut:
    with get_db() as conn:
        user_id = authenticate(conn, username=payload.username, password=payload.password)
        if not user_id:
            raise HTTPException(status_code=400, detail="用户名或密码错误")
        sess = create_session(conn, user_id=user_id, ttl_hours=24)
        return TokenOut(token=sess.token, expires_at=sess.expires_at)


@app.post("/api/auth/logout")
def logout(user: UserOut = Depends(get_current_user), authorization: Optional[str] = Header(default=None, alias="Authorization")) -> dict:
    parts = authorization.split(" ", 1)
    token = parts[1].strip()
    with get_db() as conn:
        delete_session(conn, token)
    return {"ok": True}


@app.get("/api/me", response_model=UserOut)
def me(user: UserOut = Depends(get_current_user)) -> UserOut:
    return user


@app.post("/api/admin/users", response_model=UserOut)
def admin_create_user(payload: AdminCreateUserIn, admin: UserOut = Depends(require_role("admin"))) -> UserOut:
    with get_db() as conn:
        try:
            user_id = create_user(conn, username=payload.username, password=payload.password, role=payload.role, phone=payload.phone)
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="创建失败：用户名已存在")
        except Exception:
            raise HTTPException(status_code=400, detail="创建失败：参数不合法")
        row = get_user_by_id(conn, user_id)
        return _row_to_user_out(row)


@app.get("/api/admin/repairmen", response_model=list[UserOut])
def admin_repairmen(_: UserOut = Depends(require_role("admin"))) -> list[UserOut]:
    with get_db() as conn:
        rows = list_users_by_role(conn, "repairman")
        return [_row_to_user_out(r) for r in rows]


@app.post("/api/repairs", response_model=RepairOut)
def create_repair(payload: RepairCreateIn, student: UserOut = Depends(require_role("student"))) -> RepairOut:
    with get_db() as conn:
        request_id = create_repair_request(
            conn,
            student_id=student.id,
            title=payload.title,
            description=payload.description,
            location_building=payload.location_building,
            location_room=payload.location_room,
            contact_phone=payload.contact_phone,
        )
        row = get_repair_request(conn, request_id)
        return _row_to_repair_out(row)


@app.get("/api/repairs/mine", response_model=list[RepairOut])
def my_repairs(student: UserOut = Depends(require_role("student"))) -> list[RepairOut]:
    with get_db() as conn:
        rows = list_repair_requests_for_student(conn, student.id)
        return [_row_to_repair_out(r) for r in rows]


@app.get("/api/repairs", response_model=list[RepairOut])
def all_repairs(_: UserOut = Depends(require_role("admin", "repairman"))) -> list[RepairOut]:
    with get_db() as conn:
        rows = list_repair_requests(conn)
        return [_row_to_repair_out(r) for r in rows]


@app.get("/api/workorders", response_model=list[WorkOrderOut])
def workorders(user: UserOut = Depends(require_role("admin", "repairman"))) -> list[WorkOrderOut]:
    with get_db() as conn:
        if user.role == "repairman":
            rows = list_work_orders_for_repairman(conn, user.id)
        else:
            rows = list_work_orders(conn)
        return [_row_to_workorder_out(r) for r in rows]


@app.post("/api/workorders/{work_order_id}/assign", response_model=WorkOrderOut)
def assign(work_order_id: int, payload: WorkOrderAssignIn, user: UserOut = Depends(require_role("admin", "repairman"))) -> WorkOrderOut:
    with get_db() as conn:
        wo = get_work_order(conn, work_order_id)
        if not wo:
            raise HTTPException(status_code=404, detail="工单不存在")
        target = payload.assigned_to if payload.assigned_to is not None else user.id
        if user.role == "repairman" and target != user.id:
            raise HTTPException(status_code=403, detail="维修员只能把工单分配给自己")
        assign_work_order(conn, work_order_id=work_order_id, assigned_to=target)
        updated = get_work_order(conn, work_order_id)
        return _row_to_workorder_out(updated)


@app.post("/api/workorders/{work_order_id}/status", response_model=WorkOrderOut)
def update_status(work_order_id: int, payload: WorkOrderStatusIn, user: UserOut = Depends(require_role("admin", "repairman"))) -> WorkOrderOut:
    with get_db() as conn:
        wo = get_work_order(conn, work_order_id)
        if not wo:
            raise HTTPException(status_code=404, detail="工单不存在")
        if user.role == "repairman" and wo["assigned_to"] not in (None, user.id):
            raise HTTPException(status_code=403, detail="只能操作分配给自己的工单")
        update_work_order_status(conn, work_order_id=work_order_id, status=payload.status, note=payload.note)
        updated = get_work_order(conn, work_order_id)
        return _row_to_workorder_out(updated)


@app.get("/api/announcements", response_model=list[AnnouncementOut])
def announcements(_: UserOut = Depends(get_current_user)) -> list[AnnouncementOut]:
    with get_db() as conn:
        rows = list_announcements(conn)
        return [_row_to_announcement_out(r) for r in rows]


@app.post("/api/announcements", response_model=AnnouncementOut)
def create_announcement_api(payload: AnnouncementCreateIn, _: UserOut = Depends(require_role("admin"))) -> AnnouncementOut:
    with get_db() as conn:
        ann_id = create_announcement(conn, title=payload.title, content=payload.content)
        row = conn.execute("SELECT * FROM announcements WHERE id = ?;", (ann_id,)).fetchone()
        return _row_to_announcement_out(row)


@app.get("/api/admin/stats", response_model=StatsOut)
def admin_stats(_: UserOut = Depends(require_role("admin"))) -> StatsOut:
    with get_db() as conn:
        total, req_map, wo_map = stats(conn)
        return StatsOut(requests_total=total, requests_by_status=req_map, work_orders_by_status=wo_map)
