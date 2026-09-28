from datetime import date

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6)


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


class UserOut(BaseModel):
    id: int
    username: str


class CommunityUserOut(BaseModel):
    id: int
    username: str
    unique_cards: int  # distinct cards owned (incl. binder-only)
    total_copies: int  # physical copies, foil + non-foil
    is_self: bool  # the requesting user, so the UI can label their own row


class CardOut(BaseModel):
    id: str
    name: str
    set_code: str
    number: str
    rarity: str
    domain: str
    card_type: str
    image_url: str
    count: int  # non-foil copies
    foil_count: int  # foil copies
    in_binder: bool  # marked present in the collector's binder
    binder_foil: bool  # the binder copy is a foil
    limit: int
    limit_override: int | None = None


class TradeItem(BaseModel):
    card_id: str
    foil: bool = False
    quantity: int = Field(ge=1)


class TradeExportRequest(BaseModel):
    to_username: str
    items: list[TradeItem]


class TradeExportOut(BaseModel):
    text: str


class TradeParseRequest(BaseModel):
    text: str


class TradePreviewLine(BaseModel):
    card_id: str
    card_name: str
    image_url: str | None  # null when the card id isn't in the catalog
    foil: bool
    requested: int
    current_count: int  # the owner's count for this finish, before the trade
    resulting_count: int  # what it becomes if this line is fulfilled in full
    known: bool  # the card id resolved against the catalog
    sufficient: bool  # the owner actually holds `requested` copies


class TradePreviewOut(BaseModel):
    from_username: str | None
    to_username: str | None
    lines: list[TradePreviewLine]
    warnings: list[str]


class TradeFulfilRequest(BaseModel):
    items: list[TradeItem]


class TradeFulfilOut(BaseModel):
    applied: int  # copies actually deducted
    cards: list[CardOut]  # updated cards, for the frontend to patch in place


class InventoryPatch(BaseModel):
    count: int | None = Field(default=None, ge=0)
    foil_count: int | None = Field(default=None, ge=0)
    in_binder: bool | None = None
    binder_foil: bool | None = None
    limit_override: int | None = Field(default=None, ge=0)


class LimitRules(BaseModel):
    type_limits: dict[str, int]
    rarity_caps_enabled: bool
    rarity_caps: dict[str, int]
    fallback_limit: int = Field(ge=0)


class InventoryExportRow(BaseModel):
    card_id: str
    count: int = Field(ge=0)
    foil_count: int = Field(default=0, ge=0)
    in_binder: bool = False
    binder_foil: bool = False
    limit_override: int | None = None


class ExportPayload(BaseModel):
    version: int = 1
    rules: LimitRules
    inventory: list[InventoryExportRow]


class PriceOut(BaseModel):
    card_id: str
    configured: bool  # False when no API key is set — fields below are then all null
    market_price: float | None = None
    low_price: float | None = None
    foil_market_price: float | None = None
    foil_low_price: float | None = None
    currency: str = "USD"
    updated_at: str | None = None
    stale: bool = True
    pct_change_7d: float | None = None
    pct_change_30d: float | None = None


class PriceHistoryPoint(BaseModel):
    date: date
    market_price: float | None
    foil_market_price: float | None


class PriceHistoryOut(BaseModel):
    card_id: str
    points: list[PriceHistoryPoint]


class PriceStatusOut(BaseModel):
    configured: bool
    requests_used_today: int
    daily_budget: int
    stale_hours: int


class DeckOptionsOut(BaseModel):
    count_all_variants: bool = True
