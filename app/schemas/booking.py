import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BookingCreate(BaseModel):
    resource_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("starts_at", "ends_at")
    @classmethod
    def _assume_utc_if_naive(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @model_validator(mode="after")
    def _ends_after_starts(self) -> "BookingCreate":
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class BookingUpdate(BaseModel):
    resource_id: uuid.UUID


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


class AvailabilitySlot(BaseModel):
    starts_at: datetime
    ends_at: datetime
    status: str


class AvailabilityResponse(BaseModel):
    resource_id: uuid.UUID
    from_: datetime = Field(alias="from")
    to: datetime
    busy: list[AvailabilitySlot]
    cached: bool

    model_config = ConfigDict(populate_by_name=True)
