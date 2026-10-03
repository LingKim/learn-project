"""Immutable references selected for a learning task, independent of domain imports."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WeaknessTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["weakness"] = "weakness"
    id: UUID
    version: int = Field(ge=1)


class ExplanationTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["explanation"] = "explanation"
    id: UUID
    card_version: int = Field(ge=1)


LearningTarget = Annotated[WeaknessTarget | ExplanationTarget, Field(discriminator="kind")]
