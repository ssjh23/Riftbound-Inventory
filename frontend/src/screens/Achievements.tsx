import { useMemo, useState } from "react";

import { computeAchievements, type Achievement, type BadgeTier } from "../lib/achievements";
import type { Card } from "../types";

const TIERS: BadgeTier[] = ["bronze", "silver", "gold", "prismatic"];
const TIER_LABEL: Record<BadgeTier, string> = {
  bronze: "Bronze",
  silver: "Silver",
  gold: "Gold",
  prismatic: "Prismatic",
};

/** Hexagonal medal badge, coloured by tier — Bronze/Silver/Gold are flat
 * metallic gradients, Prismatic is an animated rainbow (echoing the foil
 * shimmer used elsewhere in the app). Ungained badges render as a dim,
 * outline-only hexagon so locked achievements still show their shape. */
function Badge({ tier, category }: { tier: BadgeTier | null; category: Achievement["category"] }) {
  const glyph = category === "completion" ? "★" : "◆";
  return (
    <div className={`badge ${tier ? `tier-${tier}` : "locked"}`} aria-hidden="true">
      {glyph}
    </div>
  );
}

function AchievementCard({ a }: { a: Achievement }) {
  const pct = a.target === 0 ? 0 : Math.min(100, Math.round((a.current / a.target) * 100));
  return (
    <div className={`achv-card ${a.tier ? "unlocked" : ""}`}>
      <Badge tier={a.tier} category={a.category} />
      <div className="achv-body">
        <div className="achv-head">
          <span className="achv-title">{a.title}</span>
          {a.tier && <span className={`achv-tier-label tier-${a.tier}`}>{TIER_LABEL[a.tier]}</span>}
        </div>
        <p className="achv-desc">{a.description}</p>
        <div className="progress">
          <div
            className={`progress-bar ${a.tier === "prismatic" ? "complete" : ""}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="achv-count">{a.current} / {a.target}</div>
      </div>
    </div>
  );
}

function Section({ title, items }: { title: string; items: Achievement[] }) {
  if (items.length === 0) return null;
  return (
    <>
      <h3 className="achv-subtitle">{title}</h3>
      <div className="achv-grid">
        {items.map((a) => (
          <AchievementCard key={a.id} a={a} />
        ))}
      </div>
    </>
  );
}

export default function Achievements({ cards }: { cards: Card[] }) {
  const [setFilter, setSetFilter] = useState("");
  const achievements = useMemo(() => computeAchievements(cards), [cards]);
  const sets = useMemo(() => [...new Set(cards.map((c) => c.set_code))].sort(), [cards]);
  const visibleSets = setFilter ? [setFilter] : sets;
  const unlockedCount = achievements.filter((a) => a.tier).length;

  const byGroup = (category: Achievement["category"], scope: Achievement["scope"], setCode?: string) =>
    achievements.filter(
      (a) => a.category === category && a.scope === scope && (scope === "global" || a.setCode === setCode),
    );

  return (
    <main className="achievements">
      <div className="metric-grid">
        <div className="metric">
          <div className="metric-label">Achievements unlocked</div>
          <div className="metric-value accent">
            {unlockedCount} / {achievements.length}
          </div>
        </div>
      </div>

      <div className="achv-legend">
        {TIERS.map((t) => (
          <div key={t} className="achv-legend-item">
            <span className={`achv-legend-swatch tier-${t}`} aria-hidden="true" />
            {TIER_LABEL[t]}
          </div>
        ))}
        <span className="hint">Badges upgrade as you collect more — Prismatic at 100%.</span>
      </div>

      <div className="filters">
        <select value={setFilter} onChange={(e) => setSetFilter(e.target.value)}>
          <option value="">All sets</option>
          {sets.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>

      <h2>Completion milestones</h2>
      {!setFilter && <Section title="Across all sets" items={byGroup("completion", "global")} />}
      {visibleSets.map((s) => (
        <Section key={`completion-${s}`} title={s} items={byGroup("completion", "set", s)} />
      ))}

      <h2>Rarity chaser</h2>
      {!setFilter && <Section title="Across all sets" items={byGroup("rarity", "global")} />}
      {visibleSets.map((s) => (
        <Section key={`rarity-${s}`} title={s} items={byGroup("rarity", "set", s)} />
      ))}
    </main>
  );
}
