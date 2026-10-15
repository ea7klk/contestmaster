"""Global, editable catalogs used by contest ruleset eligibility."""

from sqlalchemy import Boolean, CheckConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db import Base


class OperatingCatalogItem(Base):
    __tablename__ = "operating_catalog_items"
    __table_args__ = (
        UniqueConstraint("kind", "key", name="operating_catalog_kind_key_unique"),
        CheckConstraint("kind IN ('band', 'mode')", name="operating_catalog_kind"),
        CheckConstraint("length(trim(key)) > 0", name="operating_catalog_key_not_blank"),
        CheckConstraint("length(trim(label)) > 0", name="operating_catalog_label_not_blank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    frequency_range: Mapped[str | None] = mapped_column(String(120))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    contest_free: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
