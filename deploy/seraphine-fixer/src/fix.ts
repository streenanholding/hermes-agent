// Outage repair and closing the loop inside the 4-minute window.
//
// 1. Confirm it's really down (2 failed checks, 15 s apart).
// 2. Certificate or DNS problem? Never restart; repair DNS or explain.
// 3. Restart. Then check every 15 s until it's healthy twice in a row.
// 4. Still down and the newest deploy is recent? Roll back, check again.
// 5. Healthy twice in a row -> acknowledge, then resolve the Better Stack
//    incident with a note. Inside 4 minutes that means nobody gets called.
//    Not healthy (or flapping) -> leave it unacknowledged so the call goes out.
// Every incident's time-to-detect and time-to-fix is logged.

import { ackIncident, commentIncident, resolveIncident, type Incident } from "./betterstack";
import { CERT_ERROR, checkUrlFor, confirmDown, isUp, targetForUrl, urlUp, waitHealthy, type Check, type Healthy } from "./checks";
import {
  APP_SERVICE_WEB, CHECK_GAP_MS, JOURNEYS, RECENT_FIX_MS, SETTLE_MS, TARGETS, VERIFY_BUDGET_MS, WINDOW_MS,
  asTarget, type StatusTarget, type Target,
} from "./config";
import { diagnoseAlert } from "./diagnose";
import { dnsBroken, publicDns, repairDns } from "./dns";
import { canAct, record } from "./policy";
import { act, currentOf, listDeployments, planRestart, planRollback } from "./railway";
import { errText, hhmm, rt } from "./runtime";
import { followUp, post, problem } from "./slack";
import { saveState, state, type FixRecord } from "./state";

export const busy = new Set<string>(); // serviceIds (and a few task keys) with work in progress
const attached = new Map<string, Incident[]>(); // serviceId -> Better Stack incidents waiting on the fix in progress
const lastFix = new Map<string, { at: number; note: string }>(); // serviceId -> last verified fix

export function resetFix() {
  busy.clear(); attached.clear(); lastFix.clear();
}

export const STILL_DOWN_HINT =
  "If the service logs show the app running, check that the domain's target port matches the port the app listens on (Sandbox outage, Oct 12–13, was a 3000 vs 8080 mismatch).";
const CERT_HINT =
  "A restart can't fix a certificate, so I did NOT restart. Right after a DNS move this clears on its own within ~15 min. If it lasts longer, check Cloudflare → SSL/TLS is set to \"Full\", and the domain shows a green check in Railway.";

// An incident for a service she's already fixing joins that fix, so it gets
// closed when the fix is verified.
export function attachIncident(serviceId: string, inc?: Incident) {
  if (!inc?.id) return;
  const list = attached.get(serviceId) || [];
  if (!list.some((x) => x.id === inc.id)) list.push(inc);
  attached.set(serviceId, list);
}

// Outage steps: the first starts the thread; if the same outage is back within
// 6 h the original message is bumped and the new step still goes in the thread.
async function say(key: string, text: string) {
  const r = await problem(key, text);
  if (!r.isNew) await followUp(key, text);
}

const mmss = (ms: number) => `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`;

// Acknowledge, then resolve, every incident waiting on this service. Only
// ever called after waitHealthy() saw 2 healthy checks in a row.
export async function closeLoop(serviceId: string, rec: FixRecord, note: string, h: Healthy): Promise<string> {
  if (!h.healthy) throw new Error("closeLoop called without 2 healthy checks"); // never silence an unhealthy service
  const incidents = attached.get(serviceId) || [];
  attached.delete(serviceId);
  if (!incidents.length) return "No Better Stack incident to close.";
  if (!rt.env.BETTERSTACK_API_TOKEN) return "I could not close the Better Stack incident: BETTERSTACK_API_TOKEN is not set, so the call still goes out at minute 4.";
  const out: string[] = [];
  for (const inc of incidents) {
    rec.incidentIds.push(inc.id);
    const acked = await ackIncident(inc.id);
    const resolved = acked && (await resolveIncident(inc.id));
    await commentIncident(inc.id, note);
    const at = rt.now();
    if (!resolved) {
      out.push(`Better Stack refused my ${acked ? "resolve" : "acknowledge"} for incident ${inc.id} — check BETTERSTACK_API_TOKEN.`);
      continue;
    }
    rec.closedAt = at;
    const inWindow = at <= inc.startedAt + WINDOW_MS;
    rec.silenced = rec.silenced || inWindow;
    out.push(
      inWindow
        ? `Acknowledged and resolved the Better Stack incident ${mmss(at - inc.startedAt)} after it started — nobody was called.`
        : `Resolved the Better Stack incident ${mmss(at - inc.startedAt)} after it started (the call had already gone out at minute 4).`,
    );
  }
  return out.join(" ");
}

function logFix(rec: FixRecord) {
  state.fixes.push(rec);
  saveState();
  rt.log(JSON.stringify({
    event: "incident",
    service: rec.service,
    outcome: rec.outcome,
    incidents: rec.incidentIds,
    time_to_detect_s: rec.detectedAt ? Math.round((rec.detectedAt - rec.startedAt) / 1000) : null,
    time_to_fix_s: rec.fixedAt ? Math.round((rec.fixedAt - rec.startedAt) / 1000) : null,
    silenced: rec.silenced,
  }));
}

export type FixOpts = { checkUrl?: string; incident?: Incident };

export async function runFix(t: Target, token: string, opts: FixOpts = {}): Promise<FixRecord> {
  const check = (): Promise<Check> => (opts.checkUrl ? urlUp(opts.checkUrl) : isUp(t));
  const key = `down:${t.serviceId}`;
  busy.add(t.serviceId);
  attachIncident(t.serviceId, opts.incident);
  const rec: FixRecord = {
    service: t.name, serviceId: t.serviceId, incidentIds: [], startedAt: opts.incident?.startedAt ?? rt.now(),
    detectedAt: 0, silenced: false, outcome: "humans",
  };

  const verified = async (how: string, h: Healthy) => {
    rec.fixedAt = h.at;
    rec.outcome = "fixed";
    const since = hhmm((h.at || rt.now()) - CHECK_GAP_MS);
    const note = `Seraphine ${how} ${t.name} at ${hhmm(rec.actionAt || rt.now())}; healthy since ${since} (2 checks in a row).`;
    lastFix.set(t.serviceId, { at: rt.now(), note });
    const closed = await closeLoop(t.serviceId, rec, note, h);
    await followUp(key, `✅ Seraphine: ${t.name} is back up after I ${how} it (${h.detail}); healthy since ${since}. ${closed}`);
  };

  try {
    const c0 = await confirmDown(check);
    if (!c0.down) {
      rec.outcome = "up";
      const lf = lastFix.get(t.serviceId);
      if (lf && rt.now() - lf.at < RECENT_FIX_MS && attached.get(t.serviceId)?.length) {
        // The alert is about an outage she already fixed: confirm healthy twice, then close it.
        const h = await waitHealthy(check, rt.now() + 2 * CHECK_GAP_MS);
        if (h.healthy) await followUp(key, `✅ Seraphine: ${t.name} is still healthy after my fix. ${await closeLoop(t.serviceId, rec, lf.note, h)}`);
      } else {
        rt.log(`Alert for ${t.name} but it is up (${c0.detail}). No action.`);
      }
      return rec;
    }
    rec.detectedAt = rt.now();

    // Certificate guard: a restart never fixes a certificate.
    if (c0.detail === CERT_ERROR) {
      await problem(`cert:${t.serviceId}`, `🔒 Seraphine: ${t.name} has a security certificate (https lock) problem. ${CERT_HINT}`);
      return rec;
    }

    // DNS guard: never restart for a DNS problem; repair the record instead.
    const dnsIssue = await dnsBroken(t, opts.checkUrl);
    if (dnsIssue) {
      const host = new URL(opts.checkUrl || t.healthUrl).hostname;
      const fix = await repairDns(host);
      await problem(`dns:${host}`, `🌐 Seraphine: ${t.name} is unreachable because its DNS address is missing (${dnsIssue}). Not an app problem, so no restart. ${fix.msg}`);
      return rec;
    }

    // Step 1: restart.
    const p1 = planRestart(await listDeployments(t, token));
    if (p1.action === "none") {
      await say(key, `🚨 Seraphine: ${t.name} is down (${c0.detail}). ${p1.reason} No action taken. Humans needed. ${STILL_DOWN_HINT}`);
      return rec;
    }
    if (!canAct(t.serviceId)) {
      await say(key, `🛑 Seraphine: ${t.name} is down again but I've used my fixes for this hour. Stopping. Humans needed — Better Stack is calling.`);
      return rec;
    }
    await act(token, p1);
    record(t.serviceId);
    rec.action = "restart";
    rec.actionAt = rt.now();
    await say(key, `🔧 Seraphine: ${t.name} went down (${c0.detail}). ${p1.reason}`);

    await rt.sleep(SETTLE_MS);
    const h1 = await waitHealthy(check, rec.actionAt + VERIFY_BUDGET_MS);
    if (h1.healthy) {
      await verified("restarted", h1);
      return rec;
    }

    // Step 2: roll back (only if allowed and the newest deploy is recent).
    const p2 = planRollback(t, await listDeployments(t, token));
    const flap = h1.flapped ? " It is flapping (up, then down again), so I won't call it fixed." : "";
    if (p2.action === "none" || !canAct(t.serviceId)) {
      await followUp(key, `🚨 Seraphine: ${t.name} still down after restart (${h1.detail}).${flap} ${p2.action === "none" ? p2.reason : "I've used my fixes for this hour."} Humans needed — Better Stack is calling. ${STILL_DOWN_HINT}`);
      return rec;
    }
    await act(token, p2);
    record(t.serviceId);
    rec.action = "rollback";
    rec.actionAt = rt.now();
    await followUp(key, `⏪ Seraphine: ${t.name} ${p2.reason}`);

    await rt.sleep(SETTLE_MS);
    const h2 = await waitHealthy(check, rec.actionAt + VERIFY_BUDGET_MS);
    if (h2.healthy) {
      await verified("rolled back", h2);
      await followUp(key, "Review the rolled-back deploy before re-deploying it.");
    } else {
      await followUp(key, `🚨 Seraphine: ${t.name} still down after restart and rollback (${h2.detail}).${h2.flapped ? " It is flapping." : ""} Stopping. Humans needed. ${STILL_DOWN_HINT}`);
    }
    return rec;
  } catch (e: any) {
    rt.error(e);
    const msg = errText(e);
    const hint = /Not Authorized/i.test(msg) ? ` ${t.tokenVar} is expired or wrong — make a new Railway project token and paste it into my variables.` : "";
    await post(`⚠️ Seraphine fixer error on ${t.name}: ${msg}${hint}`);
    return rec;
  } finally {
    busy.delete(t.serviceId);
    attached.delete(t.serviceId); // anything still waiting stays unacknowledged: the call goes out
    if (rec.outcome !== "up") logFix(rec);
  }
}

// Known service but no token for it: still check it and say so loudly.
export async function reportNoToken(t: Target) {
  const c = await confirmDown(() => isUp(t));
  if (!c.down) return rt.log(`Alert for ${t.name} but it is up (${c.detail}). No action.`);
  await say(`down:${t.serviceId}`, `🚨 Seraphine: ${t.name} is DOWN (${c.detail}). I can't act on it: ${t.tokenVar} is not set. Humans needed. ${STILL_DOWN_HINT}`);
}

// Host we don't manage: check it ourselves and say so loudly. Never guess another service.
export async function reportUnknown(hosts: string[]) {
  const results = await Promise.all(hosts.map(async (h) => ({ h, r: await urlUp(`https://${h}`) })));
  const down = results.filter((x) => !x.r.up);
  if (!down.length) return rt.log(`Alert for unmanaged host(s) ${hosts.join(", ")} but they are up. No action.`);
  await problem(`unknown:${down.map((x) => x.h).join(",")}`,
    `🚨 Seraphine: alert for a site I don't manage: ${down.map((x) => `${x.h} (${x.r.detail})`).join(", ")}. No action taken. Humans needed.`);
}

// ---- Agent platform: services with no web address ----
const buildNote = new Map<string, string>(); // serviceId -> day already reported

export async function checkStatusTarget(s: StatusTarget) {
  const t = asTarget(s);
  if (busy.has(t.serviceId)) return;
  const token = rt.env[t.tokenVar];
  if (!token) return; // reported once a day by the self-check
  const deps = await listDeployments(t, token);
  if (!deps.length) return;

  // Newest release failed to build: the old one keeps running. Say so once a day.
  if (deps[0].status === "FAILED") {
    const day = new Date(rt.now()).toISOString().slice(0, 10);
    if (buildNote.get(t.serviceId) !== day) {
      buildNote.set(t.serviceId, day);
      await post(`🧱 Seraphine: the newest release of ${t.name} failed to build. The previous version is still running, so nothing is down — but that change never went live. Humans: check the build log in Railway.`);
    }
  }

  const cur = currentOf(deps);
  if (!cur || cur.status !== "CRASHED") return;

  const key = `down:${t.serviceId}`;
  busy.add(t.serviceId);
  try {
    await rt.sleep(15_000); // confirm: still crashed 15 seconds later
    const again = currentOf(await listDeployments(t, token));
    if (!again || again.status !== "CRASHED") return;
    if (!canAct(t.serviceId)) {
      await say(key, `🛑 Seraphine: ${t.name} has crashed again but I've used my fixes for this hour. Humans needed.`);
      return;
    }
    await act(token, { action: "restart", deploymentId: again.id, reason: "" });
    record(t.serviceId);
    await say(key, `🔧 Seraphine: ${t.name} had crashed. Restarting it.`);
    await rt.sleep(VERIFY_BUDGET_MS);
    const after = currentOf(await listDeployments(t, token));
    await followUp(key,
      after && after.status === "SUCCESS"
        ? `✅ Seraphine: ${t.name} is running again after a restart.`
        : `🚨 Seraphine: ${t.name} is still crashed after a restart (${after?.status || "unknown"}). Humans needed — check its logs in Railway.`);
  } catch (e: any) {
    rt.error(e);
    const msg = errText(e);
    await post(`⚠️ Seraphine error checking ${t.name}: ${msg}${/Not Authorized/i.test(msg) ? " RAILWAY_TOKEN_AGENTS is expired or wrong." : ""}`);
  } finally {
    busy.delete(t.serviceId);
  }
}

// ---- Alerts with no hostname (Playwright journeys, error alerts) ----
type Probe = { u: string; status: number; loc: string };

async function probe(u: string): Promise<Probe> {
  try {
    const r = await rt.fetch(u, { redirect: "manual", signal: AbortSignal.timeout(20_000) });
    return { u, status: r.status, loc: r.headers.get("location") || "" };
  } catch {
    return { u, status: 0, loc: "" };
  }
}
const broken = (p: Probe) => p.status === 0 || p.status >= 500;
const short = (u: string) => u.replace("https://", "");

export async function newestDeployNote(): Promise<string> {
  const t = TARGETS.find((x) => x.serviceId === APP_SERVICE_WEB)!;
  const token = rt.env[t.tokenVar];
  if (!token) return "";
  try {
    const cur = currentOf(await listDeployments(t, token));
    if (!cur) return "";
    const min = Math.round((rt.now() - new Date(cur.createdAt).getTime()) / 60000);
    return ` Newest app release went out ${min} min ago${min < 120 ? " — likely related" : ""}.`;
  } catch {
    return "";
  }
}

export async function scenarioReport(): Promise<{ bad: Probe[]; text: string }> {
  const first = await Promise.all(JOURNEYS.map(probe));
  let bad = first.filter(broken);
  if (bad.length) {
    await rt.sleep(15_000);
    bad = (await Promise.all(bad.map((p) => probe(p.u)))).filter(broken);
  }
  const redirects = first.filter((p) => p.status >= 300 && p.status < 400 && p.loc).map((p) => `${short(p.u)} → ${p.loc}`);
  const text = bad.length
    ? `Broken: ${bad.map((p) => `${short(p.u)} (${p.status || "unreachable"})`).join(", ")}.`
    : `Every key page loads (${first.length} checked).${redirects.length ? ` Redirects: ${redirects.join("; ")}.` : ""}`;
  return { bad, text };
}

export async function scenarioTriage(name: string, incident?: Incident) {
  busy.add("scenario");
  try {
    const r = await scenarioReport();
    if (!r.bad.length) {
      // Not an outage: diagnose the errors instead of "humans: check Better Stack".
      await diagnoseAlert(name, r.text + (await newestDeployNote()));
      return;
    }
    await problem(`alert:${name}`, `🚨 Seraphine: alert "${name}". ${r.text} Fixing now.`);
    const targets = [...new Map(r.bad.map((p) => [targetForUrl(p.u)?.serviceId, p])).values()];
    // Only one broken service: the incident is about it, so a verified fix may close it.
    // Several broken: fix each, but leave the incident for humans.
    const single = targets.length === 1;
    for (const p of targets) {
      const t = targetForUrl(p.u);
      if (!t) { await post(`🚨 Seraphine: ${short(p.u)} is broken and I don't manage it. Humans needed.`); continue; }
      if (busy.has(t.serviceId)) { if (single) attachIncident(t.serviceId, incident); continue; }
      const token = rt.env[t.tokenVar];
      if (!token) { await post(`🚨 Seraphine: ${t.name} is broken but ${t.tokenVar} is not set. Humans needed.`); continue; }
      runFix(t, token, { checkUrl: p.u, incident: single ? incident : undefined });
    }
  } catch (e: any) {
    rt.error(e);
    await post(`⚠️ Seraphine scenario triage error: ${errText(e)}`);
  } finally {
    busy.delete("scenario");
  }
}

// ---- DNS alerts (never restart; repair the record or acknowledge what she saw healthy) ----
const dnsEvents: number[] = [];

export function isDnsAlert(body: any, raw: string): boolean {
  const a = body?.data?.attributes || body?.attributes || {};
  return /dns/i.test(String(a.cause || "")) || /dns lookup failure/i.test(raw);
}

export async function dnsTriage(hosts: string[], incident: Incident) {
  for (const h of hosts) {
    const key = "dns:" + h;
    if (busy.has(key)) continue;
    busy.add(key);
    try {
      const check = () => urlUp(checkUrlFor(h));
      const c = await confirmDown(check);
      const dns = await publicDns(h);
      const now = rt.now();
      dnsEvents.push(now);
      while (dnsEvents.length && now - dnsEvents[0] > 86_400_000) dnsEvents.shift();
      const cause = dnsEvents.length >= 3 ? ` (${dnsEvents.length} DNS alerts in the last 24h.)` : "";
      if (!c.down) {
        // Ack only when healthy: 2 healthy checks in a row.
        const hc = await waitHealthy(check, rt.now() + 2 * CHECK_GAP_MS);
        let ack = " (Not acknowledged: it wasn't healthy twice in a row.)";
        if (hc.healthy) {
          if (!rt.env.BETTERSTACK_API_TOKEN) ack = " (Not acknowledged yet: BETTERSTACK_API_TOKEN is not set.)";
          else if (!incident.id) ack = " (No incident id in the alert, so nothing to acknowledge.)";
          else ack = (await ackIncident(incident.id, "Seraphine (auto: DNS blip, site confirmed up)"))
            ? " I acknowledged the incident so it stops calling."
            : " (Tried to acknowledge the incident but Better Stack refused — check BETTERSTACK_API_TOKEN.)";
        }
        await say(key, `🌐 Seraphine: DNS blip on ${h}. Site is UP (${c.detail}); public DNS: ${dns}. No restart (restarts can't fix DNS).${ack}${cause}`);
      } else {
        const fix = await repairDns(h);
        await say(key, `🚨 Seraphine: DNS alert on ${h} and the site is NOT loading (${c.detail}); public DNS: ${dns}. No restart (restarts can't fix DNS). ${fix.msg}${fix.changed ? "" : " Better Stack keeps calling."}${cause}`);
      }
    } catch (e: any) {
      rt.error(e);
      await post(`⚠️ Seraphine DNS triage error on ${h}: ${errText(e)}`);
    } finally {
      busy.delete(key);
    }
  }
}
