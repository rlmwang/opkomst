from datetime import datetime

from pydantic import BaseModel


class AdminUserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    is_approved: bool
    chapter_id: str | None
    chapter_name: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


class ApproveUserRequest(BaseModel):
    chapter_id: str


class AssignChapterRequest(BaseModel):
    chapter_id: str
