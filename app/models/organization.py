from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Organization(Base):
    __tablename__ = "organization"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
