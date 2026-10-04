"""Example 2: colorectal cancer screening check (see services/crc.py)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services import crc

router = APIRouter(prefix="/api/screening/crc", tags=["screening"])


class Location(BaseModel):
    area: str | None = None
    lat: float | None = None
    lon: float | None = None
    label: str | None = None


class Person(BaseModel):
    age: int = Field(ge=18, le=100)
    sex: str = "female"
    height_cm: float | None = None
    weight_kg: float | None = None
    bmi: float | None = None
    smoking: str = "never"
    diabetes: bool = False
    family_history: str = "none"
    youngest_relative_age: int | None = None
    history: list[str] = []
    symptoms: list[str] = []
    last_screen: str = "never"
    activity: str = "some"
    diet: str = "mixed"
    alcohol: str = "none"
    location: Location | None = None


@router.get("/options")
def options() -> dict[str, Any]:
    return crc.options()


@router.post("/assess")
def assess(p: Person) -> dict[str, Any]:
    return crc.assess(p.model_dump())
