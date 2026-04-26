from datetime import datetime

from pydantic import BaseModel


class AdminUserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    is_approved: bool
    afdeling_id: str | None
    afdeling_name: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


class ApproveUserRequest(BaseModel):
    afdeling_id: str


class AssignAfdelingRequest(BaseModel):
    afdeling_id: str
