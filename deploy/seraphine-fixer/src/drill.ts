// Monthly drill, STAGING ONLY. Proves the two promises of the 4-minute window:
//   fixable:   stop a staging service; she detects, fixes and silences the
//              incident inside 4 minutes.
//   unfixable: stop it again, but she is told not to fix it; at minute 4 the
//              call must go out (incident still unacknowledged).
// Off unless DRILL_TARGET is set. Refuses any production environment
// (policy.checkRailway only allows deploymentStop outside production).
//
// DRILL_TARGET='{"name":"Platform API (staging)","projectId":"...","environmentId":"...",
//                "serviceId":"...","healthUrl":"https://.../health","tokenVar":"RAILWAY_TOKEN_STAGING"}'
// The staging health URL needs a Better Stack monitor on the "FinVerified Sev-1"
// policy, so a real incident (and a real call, in the unfixable case) happens.

import { listIncidents } from "./betterstack";
import { PRODUCTION_ENVS, WINDOW_MS, type Target } from "./config";
import { act, currentOf, gql, listDeployments } from "./railway";
import { errText, hhmm, rt } from "./runtime";
import { post } from "./slack";
import { state } from "./state";

const noFixUntil = new Map<string, number>();

export function drillTarget(): Target | null {
  if (!rt.env.DRILL_TARGET) return null;
  try {
    const d = JSON.parse(rt.env.DRILL_TARGET);
    if (!d.environmentId || PRODUCTION_ENVS.has(d.environmentId)) return null;
    return {
      name: String(d.name || "Staging drill target"), projectId: d.projectId, environmentId: d.environmentId, serviceId: d.serviceId,
      tokenVar: d.tokenVar || "RAILWAY_TOKEN_STAGING", healthUrl: d.healthUrl, allowRollback: false,
      match: [new URL(d.healthUrl).hostname], drill: true,
    };
  } catch {
    return null;
  }
}

// During the unfixable drill she must leave the service down.
export const drillBlocksFix = (serviceId: string) => (noFixUntil.get(serviceId) || 0) > rt.now();

export async function runDrill(kind: "fixable" | "unfixable"): Promise<string> {
  const t = drillTarget();
  if (!t) return "No drill: DRILL_TARGET is not set (or points at production, which is refused).";
  const token = rt.env[t.tokenVar];
  if (!token) return `No drill: ${t.tokenVar} is not set.`;
  try {
    const cur = currentOf(await listDeployments(t, token));
    if (!cur) return "No drill: no running staging deployment.";
    if (kind === "unfixable") noFixUntil.set(t.serviceId, rt.now() + 10 * 60_000);
    const start = rt.now();
    await gql(token, `mutation($id: String!) { deploymentStop(id: $id) }`, { id: cur.id }, { drillEnv: t.environmentId });
    await post(`🧪 Seraphine drill (${kind}) started at ${hhmm(start)}: I stopped ${t.name} on purpose.${kind === "unfixable" ? " I will NOT fix it; the call must go out at minute 4." : " I have 4 minutes to fix it and silence the call."}`);

    if (kind === "fixable") {
      for (let waited = 0; waited < 7 * 60_000; waited += 30_000) {
        await rt.sleep(30_000);
        const rec = state.fixes.find((f) => f.serviceId === t.serviceId && f.detectedAt >= start);
        if (rec?.outcome === "fixed" || rec?.outcome === "humans") {
          const ok = rec.outcome === "fixed" && rec.silenced;
          const text = `🧪 Drill (fixable) ${ok ? "PASSED ✅" : "FAILED 🚨"}: detected ${Math.round((rec.detectedAt - start) / 1000)}s after the stop, ` +
            `${rec.fixedAt ? `healthy ${Math.round((rec.fixedAt - start) / 1000)}s after` : "never healthy"}; ` +
            `${rec.silenced ? "incident acknowledged and resolved inside 4 minutes, nobody called." : rec.incidentIds.length ? "incident closed too late." : "no Better Stack incident was closed (is there a monitor on the staging URL?)."}`;
          await post(text);
          return text;
        }
      }
      const text = "🧪 Drill (fixable) FAILED 🚨: no fix recorded within 7 minutes.";
      await post(text);
      return text;
    }

    // Unfixable: at 4.5 minutes the incident must still be unacknowledged (so the call went out).
    await rt.sleep(WINDOW_MS + 30_000);
    const incs = (await listIncidents(new Date(start - 60_000).toISOString(), new Date(rt.now()).toISOString())).filter((i) => i.startedAt >= start - 60_000);
    const called = incs.some((i) => !i.ackedAt || i.ackedAt - i.startedAt > WINDOW_MS);
    noFixUntil.delete(t.serviceId);
    const back = currentOf(await listDeployments(t, token));
    if (back) await act(token, { action: "restart", deploymentId: back.id, reason: "drill cleanup" });
    const text = `🧪 Drill (unfixable) ${incs.length && called ? "PASSED ✅: the incident was still unacknowledged at minute 4, so the call went out." : incs.length ? "FAILED 🚨: the incident was acknowledged before minute 4." : "INCONCLUSIVE ❔: no Better Stack incident opened (add a monitor on the staging URL)."} I restarted ${t.name} to clean up.`;
    await post(text);
    return text;
  } catch (e) {
    noFixUntil.delete(t.serviceId);
    const text = `🧪 Drill (${kind}) error: ${errText(e)}`;
    await post(text);
    return text;
  }
}
