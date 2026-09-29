from .minirag_base import SQLAlchemyBase
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid


class Parent(SQLAlchemyBase):

    __tablename__ = "parents"

    parent_id = Column(Integer, primary_key=True, autoincrement=True)
    parent_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)

    parent_text = Column(String, nullable=False)
    parent_metadata = Column(JSONB, nullable=True)
    parent_order = Column(Integer, nullable=False)

    parent_project_id = Column(Integer, ForeignKey("projects.project_id"), nullable=False)
    parent_asset_id = Column(Integer, ForeignKey("assets.asset_id"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    project = relationship("Project", back_populates="parents")
    asset = relationship("Asset", back_populates="parents")
    chunks = relationship("DataChunk", back_populates="parent")

    __table_args__ = (
        Index("ix_parent_project_id", parent_project_id),
        Index("ix_parent_asset_id", parent_asset_id),
    )
