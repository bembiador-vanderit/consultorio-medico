from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ClinicalAddendum(Base):
    __tablename__ = "clinical_addenda"

    id: Mapped[int] = mapped_column(primary_key=True)
    clinical_history_id: Mapped[int] = mapped_column(
        ForeignKey("clinical_histories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    author_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    author = relationship("User", foreign_keys=[author_user_id])

    @property
    def author_name(self) -> str:
        return self.author.full_name if self.author else "Usuario no disponible"
