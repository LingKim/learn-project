from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class LearningAttachmentView(BaseModel):
    id: UUID
    filename: str
    media_type: str
    byte_size: int
    kind: Literal["image", "document"]
