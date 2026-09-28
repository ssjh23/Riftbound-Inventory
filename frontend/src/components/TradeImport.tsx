import { useEffect, useState } from "react";

import { fulfilTradeRequest, previewTradeRequest } from "../api";
import type { Card, TradePreview, TradePreviewLine } from "../types";

/** One reviewable line: what was asked for, plus what the owner has decided
 * to actually hand over. `qty` starts at the requested amount (capped by what
 * they hold) and stays editable right up to confirmation. */
interface Row {
  line: TradePreviewLine;
  fulfil: boolean;
  qty: number;
}

const rowKey = (l: TradePreviewLine) => `${l.card_id}:${l.foil ? "foil" : "normal"}`;

export default function TradeImport({ onApplied }: { onApplied: (cards: Card[]) => void }) {
  const [stage, setStage] = useState<"closed" | "paste" | "review" | "done">("closed");
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<TradePreview | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState(0);

  const close = () => {
    setStage("closed");
    setText("");
    setPreview(null);
    setRows([]);
    setError(null);
  };

  // Escape backs out of the paste box and the review view alike.
  useEffect(() => {
    if (stage === "closed") return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [stage]);

  async function review() {
    setBusy(true);
    setError(null);
    try {
      const p = await previewTradeRequest(text);
      setPreview(p);
      setRows(
        p.lines.map((line) => ({
          line,
          // Unknown cards can't be given away, so they start unticked.
          fulfil: line.known && line.current_count > 0,
          qty: Math.min(line.requested, line.current_count),
        })),
      );
      setStage("review");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    const items = rows
      .filter((r) => r.fulfil && r.line.known && r.qty > 0)
      .map((r) => ({ card_id: r.line.card_id, foil: r.line.foil, quantity: r.qty }));
    setBusy(true);
    setError(null);
    try {
      const result = await fulfilTradeRequest(items);
      onApplied(result.cards);
      setApplied(result.applied);
      setStage("done");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const update = (key: string, patch: Partial<Row>) =>
    setRows((prev) => prev.map((r) => (rowKey(r.line) === key ? { ...r, ...patch } : r)));

  const givingTotal = rows.reduce((n, r) => n + (r.fulfil && r.line.known ? r.qty : 0), 0);

  return (
    <>
      <button className="trade-import-btn" onClick={() => setStage("paste")}>
        ⇄ Import trade request
      </button>

      {stage === "paste" && (
        <div className="modal-backdrop" onClick={close}>
          <div
            className="modal-panel trade-paste"
            role="dialog"
            aria-label="Import trade request"
            onClick={(e) => e.stopPropagation()}
          >
            <h3>Import trade request</h3>
            <p className="modal-hint">
              Paste the request another collector exported from your collection.
            </p>
            <textarea
              className="trade-textarea"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={"# RIFTBOUND TRADE REQUEST v1\n# From: alice\n\n2x UNL-003 Mosstomper Seedling"}
              rows={12}
              autoFocus
            />
            {error && <div className="banner error">{error}</div>}
            <div className="modal-actions">
              <button onClick={close}>Cancel</button>
              <button className="primary" onClick={review} disabled={busy || !text.trim()}>
                {busy ? "Reading…" : "Review request"}
              </button>
            </div>
          </div>
        </div>
      )}

      {stage === "review" && preview && (
        <div className="trade-review" role="dialog" aria-label="Review trade request">
          <div className="trade-review-panel">
            <header className="trade-review-head">
              <h3>
                Trade request
                {preview.from_username ? (
                  <>
                    {" "}from <strong>{preview.from_username}</strong>
                  </>
                ) : null}
              </h3>
              <button onClick={close} aria-label="Close">×</button>
            </header>

            {preview.warnings.map((w) => (
              <div className="banner error" key={w}>{w}</div>
            ))}

            <div className="trade-table-wrap">
              <table className="trade-table">
                <thead>
                  <tr>
                    <th>Fulfil</th>
                    <th>Card</th>
                    <th>Finish</th>
                    <th>Requested</th>
                    <th>You have</th>
                    <th>Giving</th>
                    <th>After</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const key = rowKey(r.line);
                    const giving = r.fulfil && r.line.known ? r.qty : 0;
                    const after = r.line.current_count - giving;
                    return (
                      <tr key={key} className={r.line.known ? (r.fulfil ? "" : "ignored") : "unknown"}>
                        <td>
                          <input
                            type="checkbox"
                            checked={r.fulfil}
                            disabled={!r.line.known}
                            onChange={(e) => update(key, { fulfil: e.target.checked })}
                            aria-label={`Fulfil ${r.line.card_name}`}
                          />
                        </td>
                        <td className="trade-card-cell">
                          {r.line.image_url && (
                            <img src={r.line.image_url} alt="" loading="lazy" />
                          )}
                          <span>
                            {r.line.card_name}
                            <span className="trade-card-id">{r.line.card_id}</span>
                            {!r.line.known && <span className="trade-flag">Unknown card</span>}
                            {r.line.known && !r.line.sufficient && (
                              <span className="trade-flag warn">
                                Only {r.line.current_count} available
                              </span>
                            )}
                          </span>
                        </td>
                        <td>{r.line.foil ? "Foil" : "Normal"}</td>
                        <td className="num">{r.line.requested}</td>
                        <td className="num">{r.line.current_count}</td>
                        <td className="num">
                          <input
                            type="number"
                            className="trade-qty-input"
                            min={0}
                            max={r.line.current_count}
                            value={r.qty}
                            disabled={!r.fulfil || !r.line.known}
                            onChange={(e) =>
                              update(key, {
                                qty: Math.max(
                                  0,
                                  Math.min(r.line.current_count, parseInt(e.target.value, 10) || 0),
                                ),
                              })
                            }
                            aria-label={`Copies of ${r.line.card_name} to give`}
                          />
                        </td>
                        <td className={`num trade-after ${giving > 0 ? "changed" : ""}`}>
                          {r.line.current_count} → {after}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {error && <div className="banner error">{error}</div>}

            <footer className="trade-review-foot">
              <span className="trade-total">
                Fulfilling <strong>{givingTotal}</strong> of{" "}
                {rows.reduce((n, r) => n + r.line.requested, 0)} requested copies
              </span>
              <span className="spacer" />
              <button onClick={close}>Cancel</button>
              <button className="primary" onClick={confirm} disabled={busy || givingTotal === 0}>
                {busy ? "Updating…" : "Confirm & update counts"}
              </button>
            </footer>
          </div>
        </div>
      )}

      {stage === "done" && (
        <div className="modal-backdrop" onClick={close}>
          <div
            className="modal-panel trade-done"
            role="dialog"
            aria-label="Trade fulfilled"
            onClick={(e) => e.stopPropagation()}
          >
            <h3>✔ Trade fulfilled</h3>
            <p>
              {applied} cop{applied === 1 ? "y" : "ies"} removed from your collection.
            </p>
            <div className="modal-actions">
              <button className="primary" onClick={close}>Done</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
