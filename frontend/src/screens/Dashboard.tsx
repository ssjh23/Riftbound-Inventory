import { useMemo } from "react";

import { dashboardStats, setBreakdown } from "../lib/collection";
import type { Card } from "../types";

const SET_NAMES: Record<string, string> = {
  OGN: "Origins",
  UNL: "Unleashed",
  SFD: "Spiritforged",
  OGS: "Origins - Proving Grounds",
  VEN: "Vendetta",
};

const SET_LOGOS: Record<string, string> = {
  OGN: "/set-logos/OGN.png",
  UNL: "/set-logos/UNL.jpg",
  SFD: "/set-logos/SFD.jpg",
  OGS: "/set-logos/OGS.png",
  VEN: "/set-logos/VEN.jpg",
};

export default function Dashboard({
  cards,
  onViewSet,
}: {
  cards: Card[];
  onViewSet: (setCode: string) => void;
}) {
  const stats = useMemo(() => dashboardStats(cards), [cards]);
  const sets = useMemo(() => setBreakdown(cards), [cards]);

  // Fallback: first non-token card image per set, used when no promo logo exists
  const fallbackImages = useMemo(() => {
    const map = new Map<string, string>();
    for (const card of cards) {
      if (!map.has(card.set_code) && card.image_url && !card.id.match(/-T\d+$/i)) {
        map.set(card.set_code, card.image_url);
      }
    }
    return map;
  }, [cards]);

  const metrics = [
    { label: "Cards owned", value: stats.totalCopies.toLocaleString() },
    {
      label: "Unique collected",
      value: `${stats.uniqueOwned} / ${stats.totalUnique}`,
    },
    { label: "Overall progress", value: `${stats.overallPct}%`, accent: true },
    { label: "Playsets complete", value: stats.playsetsComplete.toLocaleString() },
  ];

  return (
    <main className="dashboard">
      <div className="metric-grid">
        {metrics.map((m) => (
          <div key={m.label} className="metric">
            <div className="metric-label">{m.label}</div>
            <div className={`metric-value ${m.accent ? "accent" : ""}`}>{m.value}</div>
          </div>
        ))}
      </div>

      <h2 className="section-title">Set completion</h2>
      <div className="set-grid">
        {sets.map((s) => {
          const done = s.pct >= 100;
          const logoUrl = SET_LOGOS[s.setCode] ?? fallbackImages.get(s.setCode);
          const fullName = SET_NAMES[s.setCode] ?? s.setCode;
          return (
            <div key={s.setCode} className={`set-card ${done ? "done" : ""}`}>
              {logoUrl && (
                <div className="set-logo-wrapper">
                  <img src={logoUrl} alt={fullName} className="set-logo-img" />
                  <div className="set-logo-overlay" />
                  <div className="set-logo-label">
                    <span className="set-full-name">{fullName}</span>
                  </div>
                </div>
              )}
              <div className="set-card-body">
                <div className="set-head">
                  <span className="set-code">{s.setCode}</span>
                  <span className={`set-pct ${done ? "done" : ""}`}>{s.pct}%</span>
                </div>
                <div className="progress">
                  <div
                    className={`progress-bar ${done ? "complete" : ""}`}
                    style={{ width: `${s.pct}%` }}
                  />
                </div>
                <div className="set-foot">
                  <span>{s.owned} / {s.total} unique</span>
                  <button className="link" onClick={() => onViewSet(s.setCode)}>
                    View missing →
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {sets.length === 0 && (
        <p className="empty">No cards yet — ingest a set to get started.</p>
      )}
    </main>
  );
}
