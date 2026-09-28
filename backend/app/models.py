from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Card(Base):
    __tablename__ = "cards"

    # Card ids are set_code-collector_number slugs (e.g. "OGN-042"), validated
    # at ingest time against ^[A-Za-z0-9_-]+$ so they are safe to embed in
    # file names and URLs.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    set_code: Mapped[str] = mapped_column(String(16), index=True)
    number: Mapped[str] = mapped_column(String(16))
    rarity: Mapped[str] = mapped_column(String(32), index=True)
    domain: Mapped[str] = mapped_column(String(64), index=True)
    card_type: Mapped[str] = mapped_column(String(32), index=True)
    image_file: Mapped[str] = mapped_column(String(128))
    phash: Mapped[str] = mapped_column(String(16))  # 64-bit pHash as hex
    source_url: Mapped[str] = mapped_column(Text, default="")
    # Cached id of this card in the external pricing catalog, once matched, so
    # we don't re-search their API on every refresh. Null = not matched yet.
    price_source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    inventory: Mapped[list["InventoryItem"]] = relationship(
        back_populates="card", cascade="all, delete-orphan"
    )
    price: Mapped["CardPrice | None"] = relationship(
        back_populates="card", uselist=False, cascade="all, delete-orphan"
    )


class InventoryItem(Base):
    __tablename__ = "inventory"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    card_id: Mapped[str] = mapped_column(ForeignKey("cards.id"), primary_key=True)
    # Copies owned, split by finish. `count` is non-foil, `foil_count` is foil;
    # the two are independent tallies and their sum is the total owned.
    count: Mapped[int] = mapped_column(Integer, default=0)
    foil_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Marked as present in the collector's binder. Counts as "collected" for
    # owned/missing views, but is deliberately excluded from limit/playset math.
    in_binder: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # The binder copy is a foil. Implies in_binder (enforced in the patch route)
    # and drives the holographic shimmer even without a physical foil count.
    binder_foil: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    limit_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    card: Mapped[Card] = relationship(back_populates="inventory")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)  # JSON blob


class CardPrice(Base):
    """Latest known market price per card, one row per card, always upserted
    to the most recent fetch. `variant` distinguishes normal vs foil pricing,
    since foils of the same card command a different price — stored as two
    logical prices via the nullable foil_* columns rather than two rows, so a
    card's current price is always a single lookup."""

    __tablename__ = "card_prices"

    card_id: Mapped[str] = mapped_column(ForeignKey("cards.id"), primary_key=True)
    market_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    foil_market_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    foil_low_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    card: Mapped[Card] = relationship(back_populates="price")


class CardPriceHistory(Base):
    """Append-only daily price snapshot. This is the trend data: since the
    free pricing tier has no historical endpoint, we build our own history by
    recording one row per card per day as it gets refreshed."""

    __tablename__ = "card_price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    card_id: Mapped[str] = mapped_column(ForeignKey("cards.id"), index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    market_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    foil_market_price: Mapped[float | None] = mapped_column(Float, nullable=True)


class PriceApiUsage(Base):
    """Tracks how many pricing-API requests have been spent today, so the
    free daily quota is never exceeded. One row per UTC date."""

    __tablename__ = "price_api_usage"

    usage_date: Mapped[date] = mapped_column(Date, primary_key=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0)


class SavedDeck(Base):
    __tablename__ = "saved_decks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    legend: Mapped[str] = mapped_column(String(200), default="")
    legend_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(100), default="import")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    cards: Mapped[list["SavedDeckCard"]] = relationship(
        back_populates="deck", cascade="all, delete-orphan"
    )


class SavedDeckCard(Base):
    __tablename__ = "saved_deck_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deck_id: Mapped[int] = mapped_column(ForeignKey("saved_decks.id"), index=True)
    card_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    card_name: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    section: Mapped[str] = mapped_column(String(64), default="Mainboard")
    committed_quantity: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    deck: Mapped["SavedDeck"] = relationship(back_populates="cards")
