import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BookingCreate(BaseModel):
    resource_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    status: Literal["pending", "confirmed"] = "confirmed"
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _ends_after_starts(self) -> "BookingCreate":
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    resource_id: uuid.UUID
    user_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    status: str
    notes: str | None
