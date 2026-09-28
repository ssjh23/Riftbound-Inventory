import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from . import routes
from .config import cors_origins, data_dir
from .db import Base, make_engine, make_session_factory
from .ingest.seed import seed_database
from .models import Card


def _migrate(engine) -> None:
    """Additive migrations for databases created before a column existed.
    create_all() never alters existing tables, so add any missing columns by
    hand (SQLite ADD COLUMN is safe and idempotent via the guard)."""
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(inventory)"))}
        if "foil_count" not in cols:
            conn.execute(
                text("ALTER TABLE inventory ADD COLUMN foil_count INTEGER NOT NULL DEFAULT 0")
            )
        if "in_binder" not in cols:
            conn.execute(
                text("ALTER TABLE inventory ADD COLUMN in_binder BOOLEAN NOT NULL DEFAULT 0")
            )
        if "binder_foil" not in cols:
            conn.execute(
                text("ALTER TABLE inventory ADD COLUMN binder_foil BOOLEAN NOT NULL DEFAULT 0")
            )
        if "user_id" not in cols:
            conn.execute(
                text("ALTER TABLE inventory ADD COLUMN user_id INTEGER REFERENCES users(id)")
            )
        card_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(cards)"))}
        if "price_source_id" not in card_cols:
            conn.execute(text("ALTER TABLE cards ADD COLUMN price_source_id VARCHAR(64)"))
        sdc_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(saved_deck_cards)"))}
        if sdc_cols and "committed_quantity" not in sdc_cols:
            conn.execute(
                text("ALTER TABLE saved_deck_cards ADD COLUMN committed_quantity INTEGER NOT NULL DEFAULT 0")
            )


def create_app() -> FastAPI:
    d = data_dir()
    engine = make_engine(d / "riftbound.db")
    Base.metadata.create_all(engine)
    _migrate(engine)
    session_factory = make_session_factory(engine)

    # Auto-seed the demo set on an empty database so the app works out of the
    # box; disable with RIFTBOUND_SEED=0 once real card data is ingested.
    if os.environ.get("RIFTBOUND_SEED", "1") == "1":
        with session_factory() as db:
            if db.query(Card).count() == 0:
                seed_database(db)

    app = FastAPI(title="Riftbound Inventory")
    app.state.session_factory = session_factory

    # CORS locked to the frontend's origin(s) only — the API mutates your
    # collection, so arbitrary websites must not be able to call it from a
    # browser (https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for module in (routes.auth, routes.cards, routes.inventory, routes.settings, routes.backup, routes.prices, routes.decks, routes.community, routes.trades):
        app.include_router(module.router)

    # StaticFiles resolves paths inside the mounted directory only, which
    # prevents path traversal out of the images folder.
    app.mount("/images", StaticFiles(directory=d / "images"), name="images")
    return app


app = create_app()
