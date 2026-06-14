from sqlalchemy import DECIMAL, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MessageSource(Base):
    __tablename__ = "message_sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(nullable=False, index=True)
    document_id: Mapped[int] = mapped_column(nullable=False)
    chunk_id: Mapped[int] = mapped_column(nullable=False)
    score: Mapped[float | None] = mapped_column(DECIMAL(8, 6), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(512), nullable=True)
    doc_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
