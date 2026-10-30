// Daily IT report (8 AM ET) and weekly uptime report (Mondays, 9 AM ET).

import { spendLine, strongRiskSummary, weekSpend, capWarning } from "./ai";
import { allFindings } from "./blindspots";
import { listIncidents, monitorUptime } from "./betterstack";
import { certDaysLeft, isUp } from "./checks";
import { DEFAULT_UPTIME_TARGET, STATUS_TARGETS, TARGETS, WINDOW_MS, asTarget } from "./config";
import { goodDns, inZone } from "./dns";
import { currentOf, listDeployments, replicas } from "./railway";
import { rt } from "./runtime";
import { post } from "./slack";
import { state } from "./state";

// Domain registration expiry (public registry lookup). Best effort.
async function domainDaysLeft(domain: string): Promise<number | null> {
  try {
    const r = await rt.fetch(`https://rdap.org/domain/${domain}`, { redirect: "follow", signal: AbortSignal.timeout(15_000) });
    if (!r.ok) return null;
    const j: any = await r.json();
    const ev = (j.events || []).find((e: any) => /expiration/i.test(String(e.eventAction)));
    if (!ev?.eventDate) return null;
    return Math.floor((new Date(ev.eventDate).getTime() - rt.now()) / 86_400_000);
  } catch { return null; }
}

const icon = (ok: boolean | null) => (ok === true ? "✅" : ok === false ? "🚨" : "❔");

export async function dailyReport(): Promise<string> {
  const lines: string[] = [];
  for (const t of TARGETS) {
    const r = await isUp(t);
    const host = new URL(t.healthUrl).hostname;
    const d = host.endsWith(".up.railway.app") ? null : await certDaysLeft(host);
    const certTxt = d === null ? "" : `, security cert ${d} days left${d < 30 ? " ⚠️ RENEW SOON" : ""}`;
    lines.push(`${r.up ? "✅" : "🚨"} ${t.name}: ${r.detail}${certTxt}`);
  }
  const agentTok = rt.env.RAILWAY_TOKEN_AGENTS;
  for (const s of STATUS_TARGETS) {
    if (!agentTok) { lines.push(`❔ ${s.name}: can't see it (RAILWAY_TOKEN_AGENTS not set)`); continue; }
    try {
      const cur = currentOf(await listDeployments(asTarget(s), agentTok));
      lines.push(`${cur?.status === "SUCCESS" ? "✅" : "🚨"} ${s.name}: ${cur?.status || "no deployment"}`);
    } catch { lines.push(`⚠️ ${s.name}: RAILWAY_TOKEN_AGENTS rejected`); }
  }
  const dd = await domainDaysLeft("finverified.ai");
  lines.push(dd === null
    ? "❔ finverified.ai domain registration: couldn't read the expiry date today"
    : `${dd < 45 ? "⚠️" : "✅"} finverified.ai domain registration: ${dd} days left${dd < 45 ? " — RENEW NOW so the domain can't lapse" : ""}`);
  const saved = TARGETS.map((t) => new URL(t.healthUrl).hostname).filter(inZone);
  lines.push(rt.env.CLOUDFLARE_API_TOKEN
    ? `✅ DNS repair: working copies saved for ${saved.filter((h) => goodDns.has(h)).length} of ${saved.length} sites`
    : "⚠️ DNS repair: off (CLOUDFLARE_API_TOKEN not set)");

  lines.push("*Blind spots*");
  for (const f of await allFindings()) if (f.ok !== true || f.key.startsWith("source") || f.key === "smoke") lines.push(`${icon(f.ok)} ${f.text}`);

  const day = state.fixes.filter((f) => rt.now() - f.startedAt < 86_400_000);
  if (day.length) {
    lines.push(`*Last 24 h:* ${day.length} outage(s); fixed alone and silenced ${day.filter((f) => f.silenced).length}; people called ${day.filter((f) => !f.silenced).length}.`);
  }
  lines.push(await spendLine());
  const warn = await capWarning();
  const text = `🗓️ Seraphine daily IT report\n${lines.join("\n")}`;
  await post(text);
  if (warn) await post(warn);
  return text;
}

const median = (xs: number[]) => {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
};
const fmt = (ms: number | null) => (ms === null ? "n/a" : ms < 60_000 ? `${Math.round(ms / 1000)}s` : `${(ms / 60_000).toFixed(1)} min`);

export async function weeklyReport(): Promise<string> {
  const to = new Date(rt.now());
  const from = new Date(rt.now() - 7 * 86_400_000);
  const target = Number(rt.env.UPTIME_TARGET || DEFAULT_UPTIME_TARGET);
  const lines: string[] = [`📈 Seraphine weekly uptime report (${from.toISOString().slice(0, 10)} → ${to.toISOString().slice(0, 10)})`];

  // Uptime per service vs target.
  const up = rt.env.BETTERSTACK_API_TOKEN ? await monitorUptime(from.toISOString().slice(0, 10), to.toISOString().slice(0, 10)) : [];
  if (!up.length) lines.push("❔ Uptime: can't read Better Stack monitors (BETTERSTACK_API_TOKEN).");
  for (const u of up) {
    if (u.availability === null) continue;
    lines.push(`${u.availability >= target ? "✅" : "⚠️"} ${u.name}: ${u.availability.toFixed(3)}% (target ${target}%)`);
  }

  // Incidents, time to detect / fix, fixed alone vs paged.
  const incs = rt.env.BETTERSTACK_API_TOKEN ? await listIncidents(from.toISOString(), to.toISOString()) : [];
  const fixes = state.fixes.filter((f) => f.startedAt >= from.getTime());
  const alone = incs.filter((i) => /seraphine/i.test(i.resolvedBy) && i.resolvedAt !== undefined && i.resolvedAt - i.startedAt <= WINDOW_MS);
  const ttd = median(fixes.filter((f) => f.detectedAt).map((f) => f.detectedAt - f.startedAt));
  const ttf = median(incs.filter((i) => i.resolvedAt).map((i) => i.resolvedAt! - i.startedAt));
  lines.push(`*Incidents:* ${incs.length}. Fixed by Seraphine alone (nobody called): ${alone.length}. Paged people: ${incs.length - alone.length}.`);
  lines.push(`*Time to detect* (median, her check after the alert): ${fmt(ttd)} · *time to fix* (median, start → resolved): ${fmt(ttf)}`);

  // Risks: code-detected facts first; seraphine-strong summarises once a week.
  const facts: string[] = [];
  const apiT = TARGETS[0];
  const apiTok = rt.env[apiT.tokenVar];
  const n = apiTok ? await replicas(apiT, apiTok) : null;
  if (n !== null && n < 2) facts.push(`API runs ${n} replica: one crash or restart = downtime. Fix: 2 replicas once background jobs are single-run (advisory locks).`);
  for (const f of await allFindings()) if (f.ok === false) facts.push(f.text);
  const repeat = Object.entries(fixes.reduce((m, f) => ((m[f.service] = (m[f.service] || 0) + 1), m), {} as Record<string, number>)).filter(([, c]) => c >= 2);
  for (const [s, c] of repeat) facts.push(`${s} went down ${c} times this week: find the root cause rather than restarting.`);
  const fallback = facts.slice(0, 3).map((x, i) => `${i + 1}. ${x}`).join("\n") || "1. No open risks found by code checks.";
  const summary = facts.length ? await strongRiskSummary(facts.join("\n")) : null;
  lines.push(`*Top risks*\n${summary || fallback}`);

  // Spend.
  const spend = weekSpend();
  lines.push(`💸 AI this week: $${spend.toFixed(2)} · cost per incident $${incs.length ? (spend / incs.length).toFixed(2) : "0.00"} · AI calls ${state.ai.calls} · avoided by rulebook ${state.ai.avoidedRulebook}, by cache ${state.ai.avoidedCache}`);
  const text = lines.join("\n");
  await post(text);
  return text;
}
