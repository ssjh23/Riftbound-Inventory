import io
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..deps import get_db
from ..limits import get_rules, save_rules
from ..models import Card, InventoryItem, User
from ..schemas import ExportPayload, InventoryExportRow

router = APIRouter(prefix="/api/backup", tags=["backup"])


@router.get("/export", response_model=ExportPayload)
def export_inventory(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(InventoryItem)
        .filter(
            InventoryItem.user_id == current_user.id,
            (InventoryItem.count > 0)
            | (InventoryItem.foil_count > 0)
            | (InventoryItem.in_binder.is_(True))
            | (InventoryItem.limit_override.isnot(None)),
        )
        .all()
    )
    return ExportPayload(
        rules=get_rules(db, current_user.id),
        inventory=[
            InventoryExportRow(
                card_id=r.card_id,
                count=r.count,
                foil_count=r.foil_count,
                in_binder=r.in_binder,
                binder_foil=r.binder_foil,
                limit_override=r.limit_override,
            )
            for r in rows
        ],
    )


@router.post("/import")
def import_inventory(
    payload: ExportPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    save_rules(db, current_user.id, payload.rules.model_dump())
    applied, skipped = 0, 0
    for row in payload.inventory:
        # Unknown card ids (e.g. sets not ingested yet) are skipped, not errors.
        if db.get(Card, row.card_id) is None:
            skipped += 1
            continue
        inv = db.get(InventoryItem, (current_user.id, row.card_id))
        if inv is None:
            inv = InventoryItem(user_id=current_user.id, card_id=row.card_id)
            db.add(inv)
        inv.count = row.count
        inv.foil_count = row.foil_count
        inv.in_binder = row.in_binder
        inv.binder_foil = row.binder_foil
        inv.limit_override = row.limit_override
        applied += 1
    db.commit()
    return {"applied": applied, "skipped": skipped}


# ---------------------------------------------------------------------------
# Excel template — a spreadsheet form of the collection for offline editing.
# The download is BOTH a physical backup (prefilled with your current counts)
# and an ingest template: the layout is stable, so users can edit counts /
# binder flags in Excel and upload the same file to re-apply them.
#
# Layout (sheet "Collection", row 1 = header, frozen):
#   A Card ID   B Set     C Number      D Name    E Rarity   -- reference cols
#   F Count    G Foil count   H In binder   I Binder foil   J Limit override
# ---------------------------------------------------------------------------
XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_XLSX_BYTES = 10 * 1024 * 1024
NUMBER_KEY_RE = re.compile(r"\d+")

TEMPLATE_COLUMNS = [
    "Card ID", "Set", "Number", "Name", "Rarity",
    "Count", "Foil count", "In binder", "Binder foil", "Limit override",
]
COLUMN_WIDTHS = [18, 6, 8, 32, 11, 8, 12, 12, 14, 16]


def _number_key(number: str) -> tuple[int, str]:
    m = NUMBER_KEY_RE.match(number or "")
    return (int(m.group()) if m else 10**9, number or "")


def _to_int(value, default: int = 0) -> int:
    """Read an integer from a spreadsheet cell that might be missing, a float,
    or a string typed by the user. Clamped at 0 so negatives can't slip in."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return max(0, int(value))
    try:
        return max(0, int(str(value).strip()))
    except ValueError:
        return default


def _to_bool(value) -> bool:
    """Accept native Excel booleans, "TRUE"/"FALSE"/"YES"/"NO" strings, and
    numbers (0 = false, anything else = true). Blank = false."""
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().upper() in {"TRUE", "YES", "Y", "1"}


def _to_limit(value) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        v = int(value)
        return v if v >= 0 else None
    try:
        v = int(str(value).strip())
        return v if v >= 0 else None
    except ValueError:
        return None


def _build_workbook(rows: list[tuple[Card, InventoryItem | None]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Collection"
    ws.append(TEMPLATE_COLUMNS)

    header_font = Font(bold=True, color="FFFFFFFF")
    header_fill = PatternFill("solid", fgColor="FF2C2E38")
    ref_font = Font(color="FF808080")  # signal that these columns are for reference
    center = Alignment(horizontal="center")
    for i, cell in enumerate(ws[1], start=1):
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center
    ws.freeze_panes = "A2"

    for card, inv in rows:
        ws.append([
            card.id,
            card.set_code,
            card.number,
            card.name,
            card.rarity,
            inv.count if inv else 0,
            inv.foil_count if inv else 0,
            bool(inv.in_binder) if inv else False,
            bool(inv.binder_foil) if inv else False,
            inv.limit_override if inv else None,
        ])
    # Grey out the reference columns and centre the boolean/limit columns.
    max_row = ws.max_row
    for col in range(1, 6):  # A-E: reference
        for r in range(2, max_row + 1):
            ws.cell(row=r, column=col).font = ref_font
    for col in (8, 9):  # H,I: bools
        for r in range(2, max_row + 1):
            ws.cell(row=r, column=col).alignment = center

    for i, width in enumerate(COLUMN_WIDTHS, start=1):
        ws.column_dimensions[chr(64 + i)].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@router.get("/excel")
def export_excel(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cards = db.query(Card).all()
    cards.sort(key=lambda c: (c.set_code, _number_key(c.number)))
    inv_by_id = {
        i.card_id: i
        for i in db.query(InventoryItem).filter(InventoryItem.user_id == current_user.id).all()
    }
    rows = [(c, inv_by_id.get(c.id)) for c in cards]
    xlsx = _build_workbook(rows)
    filename = f"riftbound-collection-{date.today().isoformat()}.xlsx"
    return StreamingResponse(
        iter([xlsx]),
        media_type=XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/excel")
async def import_excel(
    file: UploadFile,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Apply counts + flags from an uploaded template. `card_id` (column A)
    identifies each row; only rows whose id matches a known card are applied,
    the rest are counted as skipped. Rows the user removes are left alone."""
    name = (file.filename or "").lower()
    if not name.endswith(".xlsx"):
        raise HTTPException(415, "expected an .xlsx file")
    data = await file.read(MAX_XLSX_BYTES + 1)
    if len(data) > MAX_XLSX_BYTES:
        raise HTTPException(413, "file too large")
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(422, "could not read the .xlsx file")
    ws = wb.active

    applied, skipped = 0, 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or row[0] is None:
            continue
        card_id = str(row[0]).strip()
        if not card_id or card_id == TEMPLATE_COLUMNS[0]:  # defensive: header
            continue
        card = db.get(Card, card_id)
        if card is None:
            skipped += 1
            continue

        # Pad row to full width so short rows (blank trailing cells) don't error.
        cells = list(row) + [None] * (len(TEMPLATE_COLUMNS) - len(row))
        count = _to_int(cells[5])
        foil_count = _to_int(cells[6])
        in_binder = _to_bool(cells[7])
        binder_foil = _to_bool(cells[8])
        limit_override = _to_limit(cells[9])
        # Backend invariant: a foil binder copy is by definition in the binder.
        if binder_foil:
            in_binder = True

        inv = db.get(InventoryItem, (current_user.id, card_id))
        if inv is None:
            inv = InventoryItem(
                user_id=current_user.id, card_id=card_id,
                count=0, foil_count=0, in_binder=False, binder_foil=False,
            )
            db.add(inv)
        inv.count = count
        inv.foil_count = foil_count
        inv.in_binder = in_binder
        inv.binder_foil = binder_foil
        inv.limit_override = limit_override
        applied += 1
    db.commit()
    return {"applied": applied, "skipped": skipped}
