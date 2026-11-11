// HTTP entry points, patrol and schedules.
//   POST /betterstack  Better Stack incident webhook (no secret needed: she verifies herself)
//   GET  /test?key=... dry runs and on-demand reports (password-protected)
//   GET  /health

import { aiGate } from "./ai";
import { incidentOf, isResolvedEvent } from "./betterstack";
import { blindSpotWatch, allFindings } from "./blindspots";
import { hostsIn, isUp, resolveTarget, urlUp, checkUrlFor, confirmDown } from "./checks";
import { PATROL_MS, STATUS_TARGETS, TARGETS, asTarget, type Target } from "./config";
import { cfRecords, describe, goodDns, inZone, publicDns, repairDns, snapshotDns, dnsBroken, zoneId } from "./dns";
import { drillBlocksFix, drillTarget, runDrill } from "./drill";
import { busy, checkStatusTarget, dnsTriage, isDnsAlert, newestDeployNote, reportNoToken, reportUnknown, runFix, scenarioReport, scenarioTriage, attachIncident } from "./fix";
import { canAct } from "./policy";
import { currentOf, listDeployments, planRestart, planRollback } from "./railway";
import { dailyReport, weeklyReport } from "./reports";
import { errText, rt } from "./runtime";
import { patternOf } from "./scrub";
import { followUp, post, problem, closeThread } from "./slack";
import { loadState } from "./state";
import { telemetryReady } from "./telemetry";

export const allTargets = (): Target[] => {
  const d = drillTarget();
  return d ? [...TARGETS, d] : TARGETS;
};

export async function handleWebhook(req: Request): Promise<Response> {
  const receivedAt = rt.now();
  const raw = await req.text();
  let body: any = {};
  try { body = JSON.parse(raw); } catch { /* match on raw text */ }
  if (isResolvedEvent(body)) return Response.json({ ok: true, msg: "Resolved/ack event ignored." });
  const incident = incidentOf(body, receivedAt);

  // DNS alerts first: never restart or roll back for DNS.
  if (isDnsAlert(body, raw)) {
    const hosts = hostsIn(raw);
    if (hosts.length) {
      dnsTriage(hosts, incident); // background
      return Response.json({ ok: true, msg: `DNS alert for ${hosts.join(", ")}: checking. Never restarting for DNS.` });
    }
  }

  const r = resolveTarget(raw, allTargets());
  if (r.unknown.length) {
    reportUnknown(r.unknown);
    return Response.json({ ok: false, msg: `Unmanaged host(s): ${r.unknown.join(", ")}. Checking and escalating.` });
  }
  const t = r.target;
  if (!t) {
    if (busy.has("scenario")) return Response.json({ ok: true, msg: "Already checking the journeys." });
    scenarioTriage(incident.name || raw.slice(0, 120), incident); // background
    return Response.json({ ok: true, msg: "No hostname in alert. Checking every key page, then diagnosing." });
  }
  if (drillBlocksFix(t.serviceId)) {
    post(`🧪 Seraphine: alert for ${t.name} during the unfixable drill. Not fixing on purpose; the call must go out at minute 4.`);
    return Response.json({ ok: true, msg: "Drill: not fixing on purpose." });
  }
  if (busy.has(t.serviceId)) {
    attachIncident(t.serviceId, incident); // closed with the fix already in progress
    return Response.json({ ok: true, msg: "Already handling this one; the incident joins that fix." });
  }
  const token = rt.env[t.tokenVar];
  if (!token) {
    reportNoToken(t);
    return Response.json({ ok: false, msg: `${t.tokenVar} not set. Checking and escalating.` });
  }
  runFix(t, token, { incident }); // background: reply to Better Stack right away
  return Response.json({ ok: true, msg: `Checking ${t.name}` });
}

async function dryRun(text: string) {
  if (text.startsWith("dns:")) {
    const h = text.slice(4);
    const c = await confirmDown(() => urlUp(checkUrlFor(h)));
    return {
      ok: true,
      msg: `[TEST — nothing changed] DNS check ${h}: site ${c.down ? "DOWN" : "UP"} (${c.detail}); public DNS: ${await publicDns(h)}. Better Stack token ${rt.env.BETTERSTACK_API_TOKEN ? "set" : "NOT set"}. Cloudflare token ${rt.env.CLOUDFLARE_API_TOKEN ? "set" : "NOT set"}; saved working copy of this record: ${goodDns.has(h) ? "yes" : "not yet"}. Never restarts for DNS.`,
    };
  }
  if (text === "cloudflare") {
    if (!rt.env.CLOUDFLARE_API_TOKEN) return { ok: false, msg: "[TEST] CLOUDFLARE_API_TOKEN is not set yet, so I can't repair DNS." };
    try {
      const lines: string[] = [];
      for (const t of TARGETS) {
        const h = new URL(t.healthUrl).hostname;
        if (!inZone(h)) continue;
        lines.push(`${h}: Cloudflare has ${describe(await cfRecords(h))}; saved working copy: ${goodDns.has(h) ? "yes" : "not yet"}`);
      }
      return { ok: true, msg: `[TEST — nothing changed] Cloudflare key works. ${lines.join("; ")}` };
    } catch (e) {
      return { ok: false, msg: `[TEST] Cloudflare key problem: ${errText(e)}` };
    }
  }
  if (text === "scenario") {
    const r = await scenarioReport();
    return { ok: true, msg: `[TEST — nothing changed] ${r.text}${r.bad.length ? " Would restart/roll back the broken service." : " Would NOT touch production."}${await newestDeployNote()}` };
  }
  if (text === "agents") {
    const token = rt.env.RAILWAY_TOKEN_AGENTS;
    if (!token) return { ok: false, msg: "[TEST] RAILWAY_TOKEN_AGENTS is not set yet, so I can't see the agent services." };
    const lines: string[] = [];
    for (const s of STATUS_TARGETS) {
      try { lines.push(`${s.name}: ${currentOf(await listDeployments(asTarget(s), token))?.status || "no deployment"}`); }
      catch (e) { lines.push(`${s.name}: token rejected (${errText(e).slice(0, 80)})`); }
    }
    return { ok: true, msg: `[TEST — nothing changed] ${lines.join("; ")}` };
  }
  if (text === "blindspots") {
    return { ok: true, msg: `[TEST — nothing posted] ${(await allFindings()).map((f) => `${f.ok === true ? "OK" : f.ok === false ? "BAD" : "?"}: ${f.text}`).join(" | ")}` };
  }
  if (text.startsWith("diagnose:")) {
    // Rulebook/cache only; never spends AI from a test.
    const p = patternOf(text.slice(9));
    const { matchRule, ruleText } = await import("./rulebook");
    const m = matchRule(p);
    return { ok: true, msg: `[TEST] pattern "${p}": ${m ? ruleText(m) : "not in the rulebook (a real alert would use the AI cache or seraphine-fast)."}` };
  }
  const r = resolveTarget(text, allTargets());
  if (r.unknown.length) return { ok: false, msg: `Unmanaged host(s): ${r.unknown.join(", ")}. Would report "humans needed".` };
  const t = r.target;
  if (!t) return { ok: false, msg: "No matching service for that target." };
  const token = rt.env[t.tokenVar];
  if (!token) return { ok: false, msg: `${t.name}: ${t.tokenVar} is not set yet. Would check the site and report "humans needed" if down.` };
  try {
    const deps = await listDeployments(t, token);
    const p1 = planRestart(deps);
    const p2 = planRollback(t, deps);
    const now = await isUp(t);
    return {
      ok: true,
      msg: `[TEST — nothing changed] ${t.name}. Token works. Site is ${now.up ? "UP" : "DOWN"} (${now.detail}). If it were down, step 1 would: ${p1.action} — ${p1.reason} If still down, step 2 would: ${p2.action} — ${p2.reason} If healthy twice in a row inside 4 minutes, I'd acknowledge and resolve the incident.`,
    };
  } catch (e) {
    return { ok: false, msg: `[TEST] ${t.name}: ${t.tokenVar} does NOT work (${errText(e).slice(0, 120)}). Make a new Railway project token.` };
  }
}

// Key check: confirm every key works and say so in #alerts.
export async function selfCheck(label = "started") {
  const seen = new Set<string>();
  const ok: string[] = [];
  const bad: string[] = [];
  for (const t of [...allTargets(), ...STATUS_TARGETS.map(asTarget)]) {
    if (seen.has(t.tokenVar)) continue;
    seen.add(t.tokenVar);
    const tok = rt.env[t.tokenVar];
    if (!tok) { bad.push(`${t.tokenVar} (not set)`); continue; }
    try { await listDeployments(t, tok); ok.push(t.tokenVar); }
    catch { bad.push(`${t.tokenVar} (rejected)`); }
  }
  let cfTxt = " Cloudflare key NOT set (I can spot DNS problems but can't repair them).";
  if (rt.env.CLOUDFLARE_API_TOKEN) {
    try { await zoneId(); cfTxt = " Cloudflare key works (I can repair DNS)."; }
    catch (e) { cfTxt = ` Cloudflare key NOT working (${errText(e).slice(0, 120)}).`; }
  }
  const bs = rt.env.BETTERSTACK_API_TOKEN ? " Better Stack key is set (I can silence incidents I fixed)." : " Better Stack key NOT set (I can't silence incidents I fixed, so the call always goes out).";
  const hb = rt.env.BETTERSTACK_HEARTBEAT_URL ? " Heartbeat is on." : " Heartbeat NOT set (nobody will know if I get stuck).";
  const tel = telemetryReady() ? " Log reading is on." : " Log reading NOT set (BETTERSTACK_SQL_*): I can't diagnose error alerts or watch log sources.";
  const gh = rt.env.GITHUB_ACTIONS_TOKEN ? " Smoke-test watch is on." : " GITHUB_ACTIONS_TOKEN NOT set (I can't watch e2e-prod-smoke).";
  const slackT = rt.env.SLACK_BOT_TOKEN && rt.env.SLACK_ALERTS_CHANNEL ? " Slack threads are on." : " Slack threads NOT set (SLACK_BOT_TOKEN + SLACK_ALERTS_CHANNEL): repeats are counted silently instead.";
  const g = await aiGate();
  const ai = g.ok ? ` AI is on (seraphine-fast, ${Math.round(g.budget?.pct || 0)}% of cap used).` : ` ${g.reason}`;
  const rest = `${cfTxt}${bs}${hb}${tel}${gh}${slackT}${ai}`;
  await post(bad.length
    ? `⚠️ Seraphine ${label}. Repair keys working: ${ok.join(", ") || "none"}. NOT working: ${bad.join(", ")} — I can't repair those until fixed.${rest}`
    : `✅ Seraphine ${label}. All ${ok.length} repair keys work.${rest}`);
}

// ---- Patrol: Seraphine checks everything herself every 5 minutes ----
const patrolDown = new Set<string>();
let patrolling = false;

// Same page, but through Railway's own address (skips our DNS). If this works
// while the real address fails, it's a DNS/domain problem — a restart won't help.
function railwayUrl(t: Target): string | null {
  const h = t.match.find((x) => x.endsWith(".up.railway.app"));
  if (!h) return null;
  const u = new URL(t.healthUrl);
  if (u.hostname === h) return null;
  return `https://${h}${u.pathname === "/" ? "" : u.pathname}`;
}

async function patrolWeb() {
  for (const t of allTargets()) {
    try {
      if (busy.has(t.serviceId) || drillBlocksFix(t.serviceId)) continue;
      const host = new URL(t.healthUrl).hostname;
      const key = `down:${t.serviceId}`;
      const r = await isUp(t);
      if (r.up) {
        await snapshotDns(host); // save the working DNS record (every 30 min)
        if (patrolDown.delete(t.serviceId)) {
          await followUp(key, `✅ Seraphine patrol: ${t.name} is answering again (${r.detail}).`);
          closeThread(key);
        }
        continue;
      }
      const ru = railwayUrl(t);
      if (ru && (await urlUp(ru)).up) {
        // App is fine; the problem is the address. Repair DNS if it's broken.
        const dnsIssue = await dnsBroken(t);
        const fix = dnsIssue
          ? await repairDns(host)
          : { changed: false, msg: r.detail === "certificate error" ? "It's the security certificate on our address. A restart can't fix that." : "Public DNS looks fine, so check the domain setup for this site in Railway and Cloudflare. Humans needed if it lasts." };
        await problem(`domain:${t.serviceId}`, `🌐 Seraphine patrol: ${t.name} fails at its real address (${r.detail}) but the app itself is fine on Railway — no restart. ${fix.msg}`);
        continue;
      }
      const token = rt.env[t.tokenVar];
      if (!token) { await reportNoToken(t); continue; }
      if (!canAct(t.serviceId)) continue; // already used this hour's fixes; Better Stack keeps calling humans
      patrolDown.add(t.serviceId);
      runFix(t, token);
    } catch (e) {
      rt.error("patrol error", t.name, e);
    }
  }
}

export async function patrol() {
  if (patrolling) return;
  patrolling = true;
  try {
    await patrolWeb();
    for (const s of STATUS_TARGETS) {
      try { await checkStatusTarget(s); } catch (e) { rt.error("agent check error", s.name, e); }
    }
    try { await blindSpotWatch(); } catch (e) { rt.error("blind-spot watch error", e); }
    // Heartbeat: "I'm alive and I finished a patrol." If this stops, Better Stack calls Rick.
    const hb = rt.env.BETTERSTACK_HEARTBEAT_URL;
    if (hb) {
      try { await rt.fetch(hb, { signal: AbortSignal.timeout(10_000) }); }
      catch { rt.error("heartbeat ping failed"); }
    }
  } finally {
    patrolling = false;
  }
}

let lastDaily = "";
let lastWeekly = "";
let lastDrill = "";

// Times are UTC: 12:00 = 8 AM ET (EDT), 13:00 Monday = 9 AM ET.
function schedules() {
  const now = new Date(rt.now());
  const day = now.toISOString().slice(0, 10);
  const h = now.getUTCHours();
  if (h === 12 && lastDaily !== day) { lastDaily = day; dailyReport().catch((e) => rt.error(e)); }
  if (now.getUTCDay() === 1 && h === 13 && lastWeekly !== day) { lastWeekly = day; weeklyReport().catch((e) => rt.error(e)); }
  // Monthly drill: first Tuesday, 15:00 UTC, only when switched on.
  if (rt.env.DRILL_SCHEDULE === "on" && now.getUTCDay() === 2 && now.getUTCDate() <= 7 && h === 15 && lastDrill !== day) {
    lastDrill = day;
    runDrill("fixable").then(() => rt.sleep(15 * 60_000)).then(() => runDrill("unfixable")).catch((e) => rt.error(e));
  }
}

export function start() {
  loadState();
  Bun.serve({
    port: Number(rt.env.PORT || 3000),
    async fetch(req) {
      const url = new URL(req.url);
      if (url.pathname === "/" || url.pathname === "/health") return Response.json({ ok: true, service: "seraphine-fixer", version: 4 });
      try {
        if (url.pathname === "/betterstack" && req.method === "POST") return await handleWebhook(req);
        // Dry runs (password-protected): GET /test?key=...&target=...
        //   sandbox.finverified.ai | dns:<host> | cloudflare | scenario | agents | blindspots | diagnose:<text>
        //   report (posts the daily report) | weekly (posts the weekly report) | drill:fixable | drill:unfixable
        if (url.pathname === "/test" && req.method === "GET") {
          const key = rt.env.FIXER_KEY;
          if (!key || url.searchParams.get("key") !== key) return new Response("forbidden", { status: 403 });
          const target = url.searchParams.get("target") || "";
          if (target === "report") { await dailyReport(); return Response.json({ ok: true, msg: "Daily report posted to #alerts." }); }
          if (target === "weekly") { await weeklyReport(); return Response.json({ ok: true, msg: "Weekly report posted to #alerts." }); }
          if (target === "drill:fixable" || target === "drill:unfixable") {
            runDrill(target.slice(6) as "fixable" | "unfixable");
            return Response.json({ ok: true, msg: "Drill started; results go to #alerts." });
          }
          return Response.json(await dryRun(target));
        }
      } catch (e) {
        rt.error(e);
        await post(`⚠️ Seraphine fixer error: ${errText(e)}`);
        return Response.json({ ok: false, msg: "error" }, { status: 500 });
      }
      return new Response("not found", { status: 404 });
    },
  });
  rt.log("seraphine-fixer v4 listening");
  setInterval(patrol, PATROL_MS);
  setInterval(schedules, 10 * 60_000);
  selfCheck("restarted");
  patrol();
}
