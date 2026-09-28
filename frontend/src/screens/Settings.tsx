import { useEffect, useRef, useState } from "react";

import {
  exportBackup,
  exportExcel,
  fetchDeckOptions,
  fetchRules,
  importBackup,
  importExcel,
  saveDeckOptions,
  saveRules,
} from "../api";
import {
  loadShineSettings,
  saveShineSettings,
  SHINE_DEFAULTS,
  SHINE_LIMITS,
  type ShineSettings,
} from "../lib/shine";
import type { DeckOptions, LimitRules } from "../types";

export default function Settings({ onRulesChanged }: { onRulesChanged: () => void }) {
  const [rules, setRules] = useState<LimitRules | null>(null);
  const [shine, setShine] = useState<ShineSettings>(loadShineSettings);
  const [deckOpts, setDeckOpts] = useState<DeckOptions | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const excelRef = useRef<HTMLInputElement>(null);

  // Persist + push to :root on every tweak so the effect updates live.
  const updateShine = (patch: Partial<ShineSettings>) => {
    const next = { ...shine, ...patch };
    setShine(next);
    saveShineSettings(next);
  };
  const resetShine = () => {
    setShine({ ...SHINE_DEFAULTS });
    saveShineSettings({ ...SHINE_DEFAULTS });
  };

  useEffect(() => {
    fetchRules().then(setRules).catch((e) => setMessage(String(e)));
    fetchDeckOptions().then(setDeckOpts).catch(() => {});
  }, []);

  if (!rules) return <main>{message ?? "Loading…"}</main>;

  const save = () =>
    saveRules(rules)
      .then((r) => {
        setRules(r);
        setMessage("Saved.");
        onRulesChanged();
      })
      .catch((e) => setMessage(String(e)));

  const doExport = async () => {
    const data = await exportBackup();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `riftbound-backup-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const doImport = async (file: File) => {
    try {
      const payload = JSON.parse(await file.text());
      const result = await importBackup(payload);
      setMessage(`Imported: ${result.applied} applied, ${result.skipped} skipped.`);
      onRulesChanged();
    } catch (e) {
      setMessage(`Import failed: ${e}`);
    }
  };

  const doExcelExport = async () => {
    try {
      const { blob, filename } = await exportExcel();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      setMessage(`Excel export failed: ${e}`);
    }
  };

  const doExcelImport = async (file: File) => {
    try {
      const result = await importExcel(file);
      setMessage(`Excel imported: ${result.applied} applied, ${result.skipped} skipped.`);
      onRulesChanged();
    } catch (e) {
      setMessage(`Excel import failed: ${e}`);
    }
  };

  return (
    <main className="settings">
      <h2>Collection limits</h2>
      <p className="hint">
        Defaults follow Riftbound deck rules: a playset of 3, one Legend, one of
        each Battlefield, 12 runes.
      </p>
      {Object.entries(rules.type_limits).map(([type, limit]) => (
        <label key={type} className="setting-row">
          <span>{type}</span>
          <input
            type="number"
            min={0}
            value={limit}
            onChange={(e) =>
              setRules({
                ...rules,
                type_limits: { ...rules.type_limits, [type]: Math.max(0, +e.target.value) },
              })
            }
          />
        </label>
      ))}
      <label className="setting-row">
        <span>
          Cap Epics at {rules.rarity_caps["epic"] ?? 1} (display collecting)
        </span>
        <input
          type="checkbox"
          checked={rules.rarity_caps_enabled}
          onChange={(e) => setRules({ ...rules, rarity_caps_enabled: e.target.checked })}
        />
      </label>
      <label className="setting-row">
        <span>Cap Showcase cards at 1 (alternate art / collector variants)</span>
        <input
          type="checkbox"
          checked={rules.showcase_cap_enabled}
          onChange={(e) => setRules({ ...rules, showcase_cap_enabled: e.target.checked })}
        />
      </label>
      <button onClick={save}>Save rules</button>

      <h2>Foil shine</h2>
      <p className="hint">
        Tunes the diagonal light sweep on foil cards. Saved per browser.
      </p>
      {(Object.keys(SHINE_LIMITS) as (keyof ShineSettings)[]).map((key) => {
        const { min, max, step, label } = SHINE_LIMITS[key];
        return (
          <label key={key} className="setting-row">
            <span>{label}</span>
            <input
              type="range"
              min={min}
              max={max}
              step={step}
              value={shine[key]}
              onChange={(e) => updateShine({ [key]: +e.target.value })}
              className="slider"
            />
            <span className="slider-value">{shine[key]}</span>
          </label>
        );
      })}
      <button onClick={resetShine}>Reset shine</button>

      <h2>Decks</h2>
      <p className="hint">Controls how card copies are counted when checking deck ownership.</p>
      {deckOpts && (
        <label className="setting-row">
          <span>Count foil &amp; binder copies toward deck requirements</span>
          <input
            type="checkbox"
            checked={deckOpts.count_all_variants}
            onChange={e => {
              const next = { ...deckOpts, count_all_variants: e.target.checked };
              setDeckOpts(next);
              saveDeckOptions(next).catch(() => {});
            }}
          />
        </label>
      )}

      <h2>Backup</h2>
      <p className="hint">
        JSON is machine-readable. Excel is a printable/editable template with
        every card prefilled — useful for offline edits or migrating between
        machines.
      </p>
      <div className="setting-row">
        <button onClick={doExport}>Export JSON</button>
        <button onClick={() => fileRef.current?.click()}>Import JSON…</button>
        <input
          ref={fileRef}
          type="file"
          accept="application/json"
          hidden
          onChange={(e) => e.target.files?.[0] && doImport(e.target.files[0])}
        />
      </div>
      <div className="setting-row">
        <button onClick={doExcelExport}>Export Excel template</button>
        <button onClick={() => excelRef.current?.click()}>Import Excel…</button>
        <input
          ref={excelRef}
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          hidden
          onChange={(e) => e.target.files?.[0] && doExcelImport(e.target.files[0])}
        />
      </div>
      {message && <div className="banner">{message}</div>}
    </main>
  );
}
