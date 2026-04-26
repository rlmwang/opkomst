from datetime import datetime

from pydantic import BaseModel


class AdminUserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    is_approved: bool
    created_at: datetime
    model_config = {"from_attributes": True}
