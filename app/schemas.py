from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


Role = Literal["student", "repairman", "admin"]
RequestStatus = Literal["submitted", "assigned", "in_progress", "done", "rejected", "cancelled"]
WorkOrderStatus = Literal["open", "assigned", "in_progress", "done", "rejected", "cancelled"]


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=100)
    dorm_building: str = Field(min_length=1, max_length=50)
    dorm_room: str = Field(min_length=1, max_length=50)
    phone: Optional[str] = Field(default=None, max_length=30)


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    token: str
    expires_at: datetime


class UserOut(BaseModel):
    id: int
    username: str
    role: Role
    dorm_building: Optional[str]
    dorm_room: Optional[str]
    phone: Optional[str]
    created_at: datetime


class AdminCreateUserIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=100)
    role: Literal["repairman", "admin"]
    phone: Optional[str] = Field(default=None, max_length=30)


class RepairCreateIn(BaseModel):
    title: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=2, max_length=2000)
    location_building: str = Field(min_length=1, max_length=50)
    location_room: str = Field(min_length=1, max_length=50)
    contact_phone: Optional[str] = Field(default=None, max_length=30)


class RepairOut(BaseModel):
    id: int
    student_id: int
    title: str
    description: str
    location_building: str
    location_room: str
    contact_phone: Optional[str]
    status: RequestStatus
    created_at: datetime
    updated_at: datetime


class WorkOrderOut(BaseModel):
    id: int
    request_id: int
    assigned_to: Optional[int]
    status: WorkOrderStatus
    note: Optional[str]
    created_at: datetime
    updated_at: datetime
    finished_at: Optional[datetime]


class WorkOrderAssignIn(BaseModel):
    assigned_to: Optional[int] = None


class WorkOrderStatusIn(BaseModel):
    status: WorkOrderStatus
    note: Optional[str] = Field(default=None, max_length=2000)


class AnnouncementCreateIn(BaseModel):
    title: str = Field(min_length=2, max_length=100)
    content: str = Field(min_length=2, max_length=5000)


class AnnouncementOut(BaseModel):
    id: int
    title: str
    content: str
    created_at: datetime


class StatsOut(BaseModel):
    requests_total: int
    requests_by_status: dict[RequestStatus, int]
    work_orders_by_status: dict[WorkOrderStatus, int]

