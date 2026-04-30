from typing import Literal

from pydantic import BaseModel


class ComponentHealth(BaseModel):
    status: Literal["ok", "error"]
    message: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    version: str
    components: dict[str, ComponentHealth]
