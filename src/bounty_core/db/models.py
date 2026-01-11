from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, Float, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SeenPost(Base):
    __tablename__ = "seen_posts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    timestamp: Mapped[float] = mapped_column(Float)


class Subscription(Base):
    __tablename__ = "subscriptions"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class GameCache(Base):
    __tablename__ = "game_cache"

    # Composite Primary Key: store + identifier
    store: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. "steam", "epic"
    identifier: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. "400", "fortnite"

    fetched_at: Mapped[float] = mapped_column(Float)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    permanent: Mapped[bool] = mapped_column(Boolean, default=False)
