"""Global, editable band and mode catalogs used by contest rulesets."""

from sqlalchemy import Boolean, CheckConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db import Base


class BandCatalogItem(Base):
    __tablename__ = "band_catalog_items"
    __table_args__ = (
        UniqueConstraint("key", name="band_catalog_key_unique"),
        CheckConstraint("length(trim(key)) > 0", name="band_catalog_key_not_blank"),
        CheckConstraint("length(trim(label)) > 0", name="band_catalog_label_not_blank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    frequency_range: Mapped[str | None] = mapped_column(String(120))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    contest_free: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ModeCatalogItem(Base):
    __tablename__ = "mode_catalog_items"
    __table_args__ = (
        UniqueConstraint("key", name="mode_catalog_key_unique"),
        CheckConstraint("length(trim(key)) > 0", name="mode_catalog_key_not_blank"),
        CheckConstraint("length(trim(label)) > 0", name="mode_catalog_label_not_blank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
