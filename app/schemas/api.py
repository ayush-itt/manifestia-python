from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class RegisterBody(BaseModel):
    deviceId: Optional[str] = Field(default=None, min_length=1)


class OnboardingSubmit(BaseModel):
    deviceId: str = Field(min_length=1)
    answers: dict[str, Any]


class MusicSearchQuery(BaseModel):
    tags: Optional[list[str]] = None
    mood: Optional[str] = None
    minDurationSec: Optional[float] = None
    maxDurationSec: Optional[float] = None
    limit: Optional[int] = Field(default=None, ge=1, le=50)


class StockSearchQuery(BaseModel):
    query: str = Field(min_length=1)
    kind: Optional[Literal["video", "image", "any"]] = None
    sources: Optional[list[Literal["pexels", "pixabay", "unsplash", "coverr", "nasa"]]] = None
    videoFirst: Optional[bool] = None
    perPage: Optional[int] = Field(default=None, ge=1, le=40)
    page: Optional[int] = Field(default=None, ge=1)
    orientation: Optional[Literal["landscape", "portrait", "square"]] = None
