// Blind-spot watch, every patrol. Catches the things that fail silently:
//   - a production log source that stopped receiving logs (alerts on it can't fire)
//   - a scheduled job whose heartbeat log line went stale (purge, billing, reminders)
//   - the latest e2e-prod-smoke run is not green
//   - a certificate that should have auto-renewed by now
//   - Postgres backups not seen in the last 24 h
// Each finding gets one #alerts thread (repeats only bump the count). With
// BLINDSPOT_PAGE=on she also opens a Better Stack incident (once per 24 h per
// finding), which calls people through the normal escalation policy.

import { createIncident } from "./betterstack";
import { certDaysLeft } from "./checks";
import { CERT_RENEW_ALARM_DAYS, DEFAULT_LOG_SILENCE_MIN, DEFAULT_SMOKE_REPO, DEFAULT_SMOKE_WORKFLOW, TARGETS } from "./config";
import { inZone } from "./dns";
import { errText, rt, timeout } from "./runtime";
import { closeThread, followUp, problem, threadOpen } from "./slack";
import { saveState, state } from "./state";
import { lastLogAt, lastMatchAt, prodSources, telemetryReady } from "./telemetry";

export type Finding = { key: string; ok: boolean | null; text: string }; // ok null = can't check (not wired)

const ago = (ms: number) => (ms < 3_600_000 ? `${Math.round(ms / 60_000)} min` : `${(ms / 3_600_000).toFixed(1)} h`);

export async function checkSources(): Promise<Finding[]> {
  if (!telemetryReady()) return [{ key: "sources", ok: null, text: "Log sources: can't check (Better Stack SQL credentials not set)." }];
  const limit = Number(rt.env.BLINDSPOT_LOG_SILENCE_MIN || DEFAULT_LOG_SILENCE_MIN) * 60_000;
  const out: Finding[] = [];
  for (const src of prodSources()) {
    const key = `source:${src}`;
    try {
      const last = await lastLogAt(src);
      const silent = last === null ? Infinity : rt.now() - last;
      out.push(silent <= limit
        ? { key, ok: true, text: `Log source ${src}: last line ${ago(silent)} ago.` }
        : { key, ok: false, text: `Log source ${src} has had no logs for ${last === null ? "over 2 days" : ago(silent)}. Alerts built on it can't fire. Check the app's Better Stack token and which source it sends to.` });
    } catch (e) {
      out.push({ key, ok: null, text: `Log source ${src}: query failed (${errText(e)}).` });
    }
  }
  return out;
}

type JobBeat = { name: string; match: string; maxHours: number; source?: string };

// JOB_HEARTBEATS='[{"name":"ID-capture purge","match":"[id-capture-retention] purge ok","maxHours":25}]'
function jobBeats(): JobBeat[] {
  try { return JSON.parse(rt.env.JOB_HEARTBEATS || "[]"); } catch { return []; }
}

export async function checkJobs(): Promise<Finding[]> {
  const beats = jobBeats();
  if (!beats.length) return [{ key: "jobs", ok: null, text: "Scheduled jobs: not wired. The purge, billing and reminder jobs don't log a success line yet (needs a small code change), so I can't tell if they ran." }];
  if (!telemetryReady()) return [{ key: "jobs", ok: null, text: "Scheduled jobs: can't check (Better Stack SQL credentials not set)." }];
  const out: Finding[] = [];
  for (const b of beats) {
    const key = `job:${b.name}`;
    try {
      const src = b.source || prodSources()[0];
      const last = await lastMatchAt(src, b.match, Math.max(b.maxHours * 2, 48));
      const age = last === null ? Infinity : rt.now() - last;
      out.push(age <= b.maxHours * 3_600_000
        ? { key, ok: true, text: `Job "${b.name}": ran ${ago(age)} ago.` }
        : { key, ok: false, text: `Job "${b.name}" hasn't logged its heartbeat for ${last === null ? `over ${Math.max(b.maxHours * 2, 48)} h` : ago(age)} (expected every ${b.maxHours} h). It may have stopped running.` });
    } catch (e) {
      out.push({ key, ok: null, text: `Job "${b.name}": query failed (${errText(e)}).` });
    }
  }
  return out;
}

export async function checkSmoke(): Promise<Finding> {
  const key = "smoke";
  const tok = rt.env.GITHUB_ACTIONS_TOKEN;
  if (!tok) return { key, ok: null, text: "Production smoke test: can't check (GITHUB_ACTIONS_TOKEN not set)." };
  const repo = rt.env.SMOKE_REPO || DEFAULT_SMOKE_REPO;
  const wf = rt.env.SMOKE_WORKFLOW || DEFAULT_SMOKE_WORKFLOW;
  try {
    const r = await rt.fetch(`https://api.github.com/repos/${repo}/actions/workflows/${wf}/runs?status=completed&per_page=10`, {
      headers: { Authorization: `Bearer ${tok}`, Accept: "application/vnd.github+json", "User-Agent": "seraphine-fixer" },
      signal: timeout(15_000),
    });
    if (!r.ok) return { key, ok: null, text: `Production smoke test: GitHub said HTTP ${r.status} (check GITHUB_ACTIONS_TOKEN can read ${repo} Actions).` };
    const runs: any[] = ((await r.json()) as any).workflow_runs || [];
    if (!runs.length) return { key, ok: null, text: `Production smoke test: no completed runs of ${wf} found.` };
    if (runs[0].conclusion === "success") return { key, ok: true, text: "Production smoke test: latest run green." };
    let n = 0;
    while (n < runs.length && runs[n].conclusion !== "success") n++;
    const since = runs[n - 1]?.created_at?.slice(0, 10) || "?";
    return { key, ok: false, text: `Production smoke test (${wf}) is red: the last ${n === runs.length ? `${n}+` : n} runs failed, since ${since}. Latest: ${runs[0].html_url}` };
  } catch (e) {
    return { key, ok: null, text: `Production smoke test: check failed (${errText(e)}).` };
  }
}

let certCache: { at: number; f: Finding[] } | null = null;
export const resetCertCache = () => { certCache = null; };

export async function checkCerts(): Promise<Finding[]> {
  if (certCache && rt.now() - certCache.at < 6 * 3_600_000) return certCache.f;
  const f: Finding[] = [];
  for (const h of [...new Set(TARGETS.map((t) => new URL(t.healthUrl).hostname).filter(inZone))]) {
    const d = await certDaysLeft(h);
    if (d === null) continue;
    f.push(d < CERT_RENEW_ALARM_DAYS
      ? { key: `cert:${h}`, ok: false, text: `Certificate for ${h} has ${d} days left; auto-renew normally happens at 30, so renewal is failing. Check the domain in Railway/Cloudflare.` }
      : { key: `cert:${h}`, ok: true, text: `Certificate for ${h}: ${d} days left.` });
  }
  certCache = { at: rt.now(), f };
  return f;
}

// BACKUP_CHECK='{"match":"pg backup completed","maxHours":24}' (a log line the backup job writes).
export async function checkBackups(): Promise<Finding> {
  const key = "backups";
  let cfg: { match?: string; maxHours?: number; source?: string } = {};
  try { cfg = JSON.parse(rt.env.BACKUP_CHECK || "{}"); } catch { /* not wired */ }
  if (!cfg.match) return { key, ok: null, text: "Postgres backups: not wired. Nothing reports a finished backup yet, so I can't confirm one ran in the last 24 h." };
  if (!telemetryReady()) return { key, ok: null, text: "Postgres backups: can't check (Better Stack SQL credentials not set)." };
  const maxH = cfg.maxHours || 24;
  try {
    const last = await lastMatchAt(cfg.source || prodSources()[0], cfg.match, 72);
    const age = last === null ? Infinity : rt.now() - last;
    return age <= maxH * 3_600_000
      ? { key, ok: true, text: `Postgres backups: last one ${ago(age)} ago.` }
      : { key, ok: false, text: `Postgres backups: none seen in the last ${last === null ? "72 h" : ago(age)} (expected every ${maxH} h).` };
  } catch (e) {
    return { key, ok: null, text: `Postgres backups: query failed (${errText(e)}).` };
  }
}

export async function allFindings(): Promise<Finding[]> {
  return [...(await checkSources()), ...(await checkJobs()), await checkSmoke(), ...(await checkCerts()), await checkBackups()];
}

// Runs every patrol. Bad findings get a thread (and optionally a page);
// a finding that clears closes its thread with a ✅.
export async function blindSpotWatch(): Promise<Finding[]> {
  const findings = await allFindings();
  for (const f of findings) {
    const key = `blind:${f.key}`;
    if (f.ok === false) {
      const { isNew } = await problem(key, `🙈 Seraphine blind spot: ${f.text}`);
      if (isNew && rt.env.BLINDSPOT_PAGE === "on" && rt.now() - (state.pages[f.key] || 0) > 86_400_000) {
        state.pages[f.key] = rt.now();
        saveState();
        const paged = await createIncident(`Seraphine blind spot: ${f.key}`, f.text);
        await followUp(key, paged ? "📟 I opened a Better Stack incident so someone is called." : "📟 I tried to page through Better Stack but it refused (check BETTERSTACK_API_TOKEN).");
      }
    } else if (f.ok === true && threadOpen(key)) {
      await followUp(key, `✅ Cleared: ${f.text}`);
      closeThread(key);
    }
  }
  return findings;
}
