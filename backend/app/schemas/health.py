from typing import Literal

from pydantic import BaseModel

CapabilityStatus = Literal["planned", "available", "unavailable"]


class Capability(BaseModel):
    id: str
    name: str
    status: CapabilityStatus
    phase: int


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str

