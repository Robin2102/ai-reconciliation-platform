from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class LocalDirectoryConfig(BaseModel):
    base_path: str = Field(..., min_length=1, description="Absolute directory to read files from")

    @field_validator("base_path")
    @classmethod
    def strip_path(cls, value: str) -> str:
        return value.strip()
