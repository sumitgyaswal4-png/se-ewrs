"""Shared response envelopes."""

from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Message(BaseModel):
    """Simple acknowledgement payload."""

    detail: str


class Page(BaseModel, Generic[T]):
    """Standard paginated collection envelope."""

    items: List[T]
    total: int = Field(description="Total rows matching the filter")
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: List[T], total: int, page: int, page_size: int) -> "Page[T]":
        pages = (total + page_size - 1) // page_size if page_size else 0
        return cls(items=items, total=total, page=page, page_size=page_size, pages=pages)


class IdResponse(BaseModel):
    id: int
    detail: str = "Created"


class OptionItem(BaseModel):
    """A value/label pair used to populate frontend select inputs."""

    value: str
    label: str
    group: Optional[str] = None
