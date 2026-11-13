from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class AthleteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    objective: str = Field(min_length=1, max_length=4000)
    timezone_name: str = 'UTC'


class AthleteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tenant_id: str
    name: str
    objective: str
    timezone_name: str
    created_at: datetime


class ObservationCreate(BaseModel):
    source: str
    observed_at: datetime
    source_version: str
    payload: dict


class RunRequest(BaseModel):
    reason: str = 'USER_REQUEST'


class AsyncRunRequest(BaseModel):
    reason: str = 'USER_REQUEST'
