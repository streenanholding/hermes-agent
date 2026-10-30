// AI metering. AI only when code can't decide.
//
// - Detection, repair, ack/resolve, dedupe, blind-spot checks and rulebook
//   matches are plain code: $0 AI.
// - Only an error pattern the rulebook doesn't match goes to a model:
//   seraphine-fast, through LiteLLM, on Seraphine's own capped virtual key.
//   Never a direct provider key, never an unmetered path.
// - Pay once per pattern: each diagnosis is cached by pattern; the same
//   pattern never calls the model again.
// - The model only sees the scrubbed pattern text and a count.
// - seraphine-strong only for the weekly risk summary, at most once a week.
// - At 80% of the cap she says so in Slack (once a day) and keeps working;
//   at 100% AI stops and every code path keeps running.

import { AI_FAST, AI_STRONG, DEFAULT_AI_CAP_USD, LITELLM_DEFAULT } from "./config";
import { patternOf, scrub } from "./scrub";
import { saveState, state } from "./state";
import { rt, timeout } from "./runtime";

const base = () => (rt.env.LITELLM_BASE_URL || LITELLM_DEFAULT).replace(/\/+$/, "").replace(/\/v1$/, "");
const key = () => rt.env.SERAPHINE_LITELLM_KEY;
const DAY = 86_400_000;

export type Budget = { spend: number; cap: number; pct: number; source: "litellm" | "local" };

let budgetCache: { at: number; b: Budget } | null = null;
export const resetBudgetCache = () => { budgetCache = null; };

function ledgerSince(ms: number) {
  return state.ai.ledger.filter((r) => rt.now() - r.at < ms).reduce((s, r) => s + r.cost, 0);
}

// The cap and spend LiteLLM holds for her key (authoritative). If LiteLLM
// can't be asked, fall back to her own ledger against the weekly cap.
export async function budget(): Promise<Budget> {
  if (budgetCache && rt.now() - budgetCache.at < 10 * 60_000) return budgetCache.b;
  let b: Budget | null = null;
  if (key()) {
    try {
      const r = await rt.fetch(`${base()}/key/info`, { headers: { Authorization: `Bearer ${key()}` }, signal: timeout(10_000) });
      if (r.ok) {
        const j: any = await r.json();
        const info = j.info || j;
        if (typeof info.spend === "number" && typeof info.max_budget === "number" && info.max_budget > 0) {
          b = { spend: info.spend, cap: info.max_budget, pct: (info.spend / info.max_budget) * 100, source: "litellm" };
        }
      }
    } catch { /* fall back to the ledger */ }
  }
  if (!b) {
    const cap = Number(rt.env.AI_WEEKLY_CAP_USD || DEFAULT_AI_CAP_USD);
    const spend = ledgerSince(7 * DAY);
    b = { spend, cap, pct: (spend / cap) * 100, source: "local" };
  }
  budgetCache = { at: rt.now(), b };
  return b;
}

export type Gate = { ok: boolean; reason: string; budget?: Budget };

export async function aiGate(): Promise<Gate> {
  if (!key()) return { ok: false, reason: "AI is off: SERAPHINE_LITELLM_KEY is not set (code-only mode)." };
  const b = await budget();
  if (b.pct >= 100) return { ok: false, reason: `AI is paused: her LiteLLM cap is used up ($${b.spend.toFixed(2)} of $${b.cap.toFixed(2)}). Code paths keep running.`, budget: b };
  return { ok: true, reason: "", budget: b };
}

// Say "AI budget at 80%" once a day.
export async function capWarning(): Promise<string | null> {
  const b = await budget();
  const day = new Date(rt.now()).toISOString().slice(0, 10);
  if (b.pct < 80 || state.ai.lastCapNoteDay === day) return null;
  state.ai.lastCapNoteDay = day;
  saveState();
  return b.pct >= 100
    ? `💸 Seraphine: my AI budget is used up ($${b.spend.toFixed(2)} of $${b.cap.toFixed(2)}). AI diagnosis is paused; restarts, rollbacks, DNS repair, rulebook diagnoses and blind-spot checks keep running. Rick: raise the cap in LiteLLM if you want AI back.`
    : `💸 Seraphine: my AI budget is at ${Math.round(b.pct)}% ($${b.spend.toFixed(2)} of $${b.cap.toFixed(2)}). I keep working; at 100% AI pauses and code-only paths keep running.`;
}

async function chat(model: string, system: string, user: string, maxTokens: number): Promise<string> {
  const r = await rt.fetch(`${base()}/v1/chat/completions`, {
    method: "POST",
    headers: { Authorization: `Bearer ${key()}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      model,
      max_tokens: maxTokens,
      temperature: 0,
      messages: [{ role: "system", content: system }, { role: "user", content: user }],
    }),
    signal: timeout(60_000),
  });
  state.ai.calls++;
  const cost = Number(r.headers.get("x-litellm-response-cost") || 0);
  state.ai.ledger.push({ at: rt.now(), cost: Number.isFinite(cost) ? cost : 0, model });
  budgetCache = null;
  saveState();
  if (!r.ok) throw new Error(`LiteLLM said HTTP ${r.status}`);
  const j: any = await r.json();
  return String(j.choices?.[0]?.message?.content || "").trim();
}

const DIAG_SYSTEM =
  "You are Seraphine, Head of IT for a small SaaS on Railway (Node API, Next.js web, Postgres, AWS S3/SSM/Bedrock, Better Stack). " +
  "You get one error pattern from production logs (ids removed) and how often it happened. " +
  "Answer in exactly 4 short lines: \"What's wrong: ...\", \"Likely cause: ...\", \"Fix: ...\", \"Who: ...\". " +
  "Who is one of: Rick (keys, IAM, secrets, money), Ashish (code and database), Seraphine (restart/rollback/DNS). " +
  "If you are not sure, say so in Likely cause. Never ask for more data.";

export type AiResult = { text: string; source: "cache" | "ai" } | { blocked: string };

// Count a rulebook hit as an AI call avoided.
export function noteRulebookHit() {
  state.ai.avoidedRulebook++;
}

export async function aiDiagnose(pattern: string, count: number): Promise<AiResult> {
  const p = patternOf(pattern); // scrub again: the model never sees anything else
  const cached = state.aiCache[p];
  if (cached) {
    state.ai.avoidedCache++;
    return { text: cached.text, source: "cache" };
  }
  const gate = await aiGate();
  if (!gate.ok) return { blocked: gate.reason };
  try {
    const text = scrub(await chat(AI_FAST, DIAG_SYSTEM, `Error pattern: ${p}\nCount in the last 30 minutes: ${count}`, 300));
    if (!text) return { blocked: "The model gave no answer." };
    state.aiCache[p] = { text, at: rt.now(), model: AI_FAST };
    saveState();
    return { text, source: "ai" };
  } catch (e: any) {
    return { blocked: `AI diagnosis failed (${String(e?.message || e).slice(0, 120)}).` };
  }
}

// ISO week label, e.g. "2026-W44".
export function weekOf(ms: number): string {
  const d = new Date(ms);
  const t = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const day = t.getUTCDay() || 7;
  t.setUTCDate(t.getUTCDate() + 4 - day);
  const y0 = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  return `${t.getUTCFullYear()}-W${String(Math.ceil(((t.getTime() - y0.getTime()) / DAY + 1) / 7)).padStart(2, "0")}`;
}

// seraphine-strong, at most once per week, for the weekly risk summary only.
export async function strongRiskSummary(facts: string): Promise<string | null> {
  const week = weekOf(rt.now());
  if (state.ai.lastStrongWeek === week) return null;
  const gate = await aiGate();
  if (!gate.ok) return null;
  state.ai.lastStrongWeek = week;
  saveState();
  try {
    return scrub(await chat(
      AI_STRONG,
      "You are Seraphine, Head of IT. From these facts, list the top 3 reliability risks, each with one concrete fix. Plain English, one line each, numbered. No preamble.",
      scrub(facts),
      400,
    ));
  } catch {
    return null;
  }
}

export async function spendLine(): Promise<string> {
  const b = await budget();
  return `💸 AI spend: today $${ledgerSince(DAY).toFixed(2)} · this week $${b.source === "litellm" ? b.spend.toFixed(2) : ledgerSince(7 * DAY).toFixed(2)} · cap $${b.cap.toFixed(2)} (${Math.round(b.pct)}%) · calls ${state.ai.calls}, avoided by rulebook ${state.ai.avoidedRulebook}, by cache ${state.ai.avoidedCache}`;
}

export function weekSpend(): number {
  return ledgerSince(7 * DAY);
}
