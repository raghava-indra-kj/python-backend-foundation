"""Dependency-free liveness endpoint."""

from typing import Literal

from fastapi import APIRouter

from .schema import ApiSchema

router = APIRouter(tags=["system"])


class HealthResponse(ApiSchema):
    status: Literal["ok"] = "ok"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()
