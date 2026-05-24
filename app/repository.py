from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Optional

import sqlite3

from .security import hash_password, new_token, verify_password


def now_utc() -> datetime:
    return datetime.now(UTC)


def _dt_to_str(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _str_to_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass(frozen=True)
class AuthSession:
    token: str
    user_id: int
    expires_at: datetime


def get_user_by_username(conn: sqlite3.Connection, username: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM users WHERE username = ?;", (username,)).fetchone()


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM users WHERE id = ?;", (user_id,)).fetchone()


def list_users_by_role(conn: sqlite3.Connection, role: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM users WHERE role = ? ORDER BY id ASC;", (role,)).fetchall()


def create_user(
    conn: sqlite3.Connection,
    *,
    username: str,
    password: str,
    role: str,
    dorm_building: Optional[str] = None,
    dorm_room: Optional[str] = None,
    phone: Optional[str] = None,
) -> int:
    created_at = _dt_to_str(now_utc())
    password_hash = hash_password(password)
    cur = conn.execute(
        """
        INSERT INTO users(username, password_hash, role, dorm_building, dorm_room, phone, created_at)
        VALUES(?,?,?,?,?,?,?);
        """,
        (username, password_hash, role, dorm_building, dorm_room, phone, created_at),
    )
    return int(cur.lastrowid)


def ensure_default_admin(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1;").fetchone()
    if existing:
        return
    create_user(conn, username="admin", password="admin123", role="admin")


def ensure_default_repairmen(conn: sqlite3.Connection) -> None:
    defaults = [
        ("rep_electric", "123456", "电路维修", "13900000001"),
        ("rep_door_bed", "123456", "门锁/床具", "13900000002"),
        ("rep_plumbing", "123456", "水龙头/下水", "13900000003"),
        ("rep_washer", "123456", "洗衣机", "13900000004"),
    ]
    for username, password, label, phone in defaults:
        exists = get_user_by_username(conn, username)
        if exists:
            continue
        create_user(conn, username=username, password=password, role="repairman", phone=f"{label} {phone}")


def create_session(conn: sqlite3.Connection, *, user_id: int, ttl_hours: int = 24) -> AuthSession:
    created_at = now_utc()
    expires_at = created_at + timedelta(hours=ttl_hours)
    token = new_token()
    conn.execute(
        "INSERT INTO sessions(token, user_id, created_at, expires_at) VALUES(?,?,?,?);",
        (token, user_id, _dt_to_str(created_at), _dt_to_str(expires_at)),
    )
    return AuthSession(token=token, user_id=user_id, expires_at=expires_at)


def delete_session(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token = ?;", (token,))


def get_session(conn: sqlite3.Connection, token: str) -> Optional[AuthSession]:
    row = conn.execute("SELECT token, user_id, expires_at FROM sessions WHERE token = ?;", (token,)).fetchone()
    if not row:
        return None
    expires_at = _str_to_dt(row["expires_at"])
    if expires_at < now_utc():
        delete_session(conn, token)
        return None
    return AuthSession(token=row["token"], user_id=int(row["user_id"]), expires_at=expires_at)


def authenticate(conn: sqlite3.Connection, *, username: str, password: str) -> Optional[int]:
    user = get_user_by_username(conn, username)
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return int(user["id"])


def create_repair_request(
    conn: sqlite3.Connection,
    *,
    student_id: int,
    title: str,
    description: str,
    location_building: str,
    location_room: str,
    contact_phone: Optional[str],
) -> int:
    created_at = now_utc()
    status = "submitted"
    cur = conn.execute(
        """
        INSERT INTO repair_requests(
          student_id, title, description, location_building, location_room, contact_phone,
          status, created_at, updated_at
        )
        VALUES(?,?,?,?,?,?,?,?,?);
        """,
        (
            student_id,
            title,
            description,
            location_building,
            location_room,
            contact_phone,
            status,
            _dt_to_str(created_at),
            _dt_to_str(created_at),
        ),
    )
    request_id = int(cur.lastrowid)
    conn.execute(
        """
        INSERT INTO work_orders(request_id, assigned_to, status, note, created_at, updated_at)
        VALUES(?,?,?,?,?,?);
        """,
        (request_id, None, "open", None, _dt_to_str(created_at), _dt_to_str(created_at)),
    )
    return request_id


def get_repair_request(conn: sqlite3.Connection, request_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM repair_requests WHERE id = ?;", (request_id,)).fetchone()


def list_repair_requests_for_student(conn: sqlite3.Connection, student_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM repair_requests WHERE student_id = ? ORDER BY id DESC;",
        (student_id,),
    ).fetchall()


def list_repair_requests(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM repair_requests ORDER BY id DESC;").fetchall()


def get_work_order(conn: sqlite3.Connection, work_order_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM work_orders WHERE id = ?;", (work_order_id,)).fetchone()


def list_work_orders(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM work_orders ORDER BY id DESC;").fetchall()


def list_work_orders_for_repairman(conn: sqlite3.Connection, repairman_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM work_orders
        WHERE assigned_to IS NULL OR assigned_to = ?
        ORDER BY id DESC;
        """,
        (repairman_id,),
    ).fetchall()


def assign_work_order(conn: sqlite3.Connection, *, work_order_id: int, assigned_to: int) -> None:
    updated_at = now_utc()
    conn.execute(
        """
        UPDATE work_orders
        SET assigned_to = ?, status = 'assigned', updated_at = ?
        WHERE id = ?;
        """,
        (assigned_to, _dt_to_str(updated_at), work_order_id),
    )
    row = get_work_order(conn, work_order_id)
    if row:
        conn.execute(
            """
            UPDATE repair_requests
            SET status = 'assigned', updated_at = ?
            WHERE id = ?;
            """,
            (_dt_to_str(updated_at), int(row["request_id"])),
        )


def update_work_order_status(conn: sqlite3.Connection, *, work_order_id: int, status: str, note: Optional[str]) -> None:
    updated_at = now_utc()
    finished_at = _dt_to_str(updated_at) if status in ("done", "rejected", "cancelled") else None
    conn.execute(
        """
        UPDATE work_orders
        SET status = ?, note = ?, updated_at = ?, finished_at = COALESCE(?, finished_at)
        WHERE id = ?;
        """,
        (status, note, _dt_to_str(updated_at), finished_at, work_order_id),
    )
    row = get_work_order(conn, work_order_id)
    if not row:
        return
    request_status_map = {
        "open": "submitted",
        "assigned": "assigned",
        "in_progress": "in_progress",
        "done": "done",
        "rejected": "rejected",
        "cancelled": "cancelled",
    }
    conn.execute(
        """
        UPDATE repair_requests
        SET status = ?, updated_at = ?
        WHERE id = ?;
        """,
        (request_status_map.get(status, "submitted"), _dt_to_str(updated_at), int(row["request_id"])),
    )


def list_announcements(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM announcements ORDER BY id DESC;").fetchall()


def create_announcement(conn: sqlite3.Connection, *, title: str, content: str) -> int:
    created_at = now_utc()
    cur = conn.execute(
        "INSERT INTO announcements(title, content, created_at) VALUES(?,?,?);",
        (title, content, _dt_to_str(created_at)),
    )
    return int(cur.lastrowid)


def stats(conn: sqlite3.Connection) -> tuple[int, dict[str, int], dict[str, int]]:
    total = int(conn.execute("SELECT COUNT(*) AS c FROM repair_requests;").fetchone()["c"])
    req_rows = conn.execute("SELECT status, COUNT(*) AS c FROM repair_requests GROUP BY status;").fetchall()
    wo_rows = conn.execute("SELECT status, COUNT(*) AS c FROM work_orders GROUP BY status;").fetchall()
    return (
        total,
        {str(r["status"]): int(r["c"]) for r in req_rows},
        {str(r["status"]): int(r["c"]) for r in wo_rows},
    )
