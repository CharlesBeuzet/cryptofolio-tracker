"""Conviction tags for positions (per asset × exchange)."""
from typing import List, Optional

from sqlalchemy.orm import Session

from ..models.database import Position, Tag


class TagService:
    """CRUD for tags and position tag assignment."""

    def __init__(self, db: Session):
        self.db = db

    def list_tags(self) -> List[Tag]:
        return self.db.query(Tag).order_by(Tag.sort_order.asc(), Tag.name.asc()).all()

    def get_tag(self, tag_id: int) -> Optional[Tag]:
        return self.db.query(Tag).filter(Tag.id == tag_id).first()

    def create_tag(
        self,
        name: str,
        color: Optional[str] = None,
        description: Optional[str] = None,
        sort_order: int = 0,
    ) -> Tag:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("Tag name is required")
        existing = self.db.query(Tag).filter(Tag.name == cleaned).first()
        if existing:
            raise ValueError(f"Tag '{cleaned}' already exists")
        tag = Tag(
            name=cleaned,
            color=color.strip() if color else None,
            description=description.strip() if description else None,
            sort_order=sort_order,
        )
        self.db.add(tag)
        self.db.commit()
        self.db.refresh(tag)
        return tag

    def update_tag(
        self,
        tag_id: int,
        name: Optional[str] = None,
        color: Optional[str] = None,
        description: Optional[str] = None,
        sort_order: Optional[int] = None,
    ) -> Tag:
        tag = self.get_tag(tag_id)
        if not tag:
            raise ValueError(f"Tag {tag_id} not found")
        if name is not None:
            cleaned = name.strip()
            if not cleaned:
                raise ValueError("Tag name is required")
            clash = (
                self.db.query(Tag)
                .filter(Tag.name == cleaned, Tag.id != tag_id)
                .first()
            )
            if clash:
                raise ValueError(f"Tag '{cleaned}' already exists")
            tag.name = cleaned
        if color is not None:
            tag.color = color.strip() or None
        if description is not None:
            tag.description = description.strip() or None
        if sort_order is not None:
            tag.sort_order = sort_order
        self.db.commit()
        self.db.refresh(tag)
        return tag

    def delete_tag(self, tag_id: int) -> bool:
        tag = self.get_tag(tag_id)
        if not tag:
            raise ValueError(f"Tag {tag_id} not found")
        # Clear assignments first (nullable FK; SQLite may not cascade)
        (
            self.db.query(Position)
            .filter(Position.tag_id == tag_id)
            .update({Position.tag_id: None}, synchronize_session=False)
        )
        self.db.delete(tag)
        self.db.commit()
        return True

    def set_position_tag(self, position_id: int, tag_id: Optional[int]) -> Position:
        position = self.db.query(Position).filter(Position.id == position_id).first()
        if not position:
            raise ValueError(f"Position {position_id} not found")
        if tag_id is not None:
            tag = self.get_tag(tag_id)
            if not tag:
                raise ValueError(f"Tag {tag_id} not found")
            position.tag_id = tag_id
        else:
            position.tag_id = None
        self.db.commit()
        self.db.refresh(position)
        return position
