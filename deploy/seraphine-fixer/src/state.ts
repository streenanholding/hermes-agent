// Small memory that survives a restart when STATE_FILE points at a Railway
// volume (for example /data/seraphine-state.json). Without it, everything
// still works; the AI cache and thread map just start empty after a restart.

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { rt } from "./runtime";

export type Thread = { ts?: string; text: string; first: number; last: number; count: number };
export type Diagnosis = { text: string; at: number; model: string; confirmed?: boolean };
export type FixRecord = {
  service: string;
  serviceId: string;
  incidentIds: string[];
  startedAt: number; // incident start (or when she first saw it fail)
  detectedAt: number; // her first failing check
  action?: string;
  actionAt?: number;
  fixedAt?: number; // second healthy check
  closedAt?: number; // acknowledged + resolved in Better Stack
  silenced: boolean; // closed before minute 4, so nobody was called
  outcome: "fixed" | "humans" | "up";
};

export type AiLedgerRow = { at: number; cost: number; model: string };

function fresh() {
  return {
    threads: {} as Record<string, Thread>,
    aiCache: {} as Record<string, Diagnosis>,
    ai: {
      calls: 0,
      avoidedRulebook: 0,
      avoidedCache: 0,
      ledger: [] as AiLedgerRow[],
      lastStrongWeek: "",
      lastCapNoteDay: "",
    },
    fixes: [] as FixRecord[],
    pages: {} as Record<string, number>, // blind-spot key -> last time it paged
  };
}

export let state = fresh();

export function resetState() {
  state = fresh();
}

export function loadState() {
  const f = rt.env.STATE_FILE;
  if (!f || !existsSync(f)) return;
  try {
    state = { ...fresh(), ...JSON.parse(readFileSync(f, "utf8")) };
  } catch (e) {
    rt.error("state file unreadable, starting fresh", e);
  }
}

export function saveState() {
  const f = rt.env.STATE_FILE;
  if (!f) return;
  const week = 8 * 86_400_000;
  state.ai.ledger = state.ai.ledger.filter((r) => rt.now() - r.at < week);
  state.fixes = state.fixes.slice(-500);
  for (const [k, t] of Object.entries(state.threads)) if (rt.now() - t.last > week) delete state.threads[k];
  try {
    writeFileSync(f, JSON.stringify(state));
  } catch (e) {
    rt.error("state file not writable", e);
  }
}
