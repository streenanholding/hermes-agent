// Better Stack Uptime API: read the incident from the webhook, acknowledge
// and resolve incidents she fixed, open an incident to page people for a
// blind spot, and read incidents/uptime for the weekly report.
// Uses BETTERSTACK_API_TOKEN (Uptime API token).

import { rt, timeout } from "./runtime";

const UPTIME = "https://uptime.betterstack.com/api";
const BY = "Seraphine (auto-fix)";

export type Incident = { id: string; startedAt: number; name: string; cause: string };

// The incident in a Better Stack webhook. started_at drives the 4-minute
// window; if it's missing we count from when the webhook arrived.
export function incidentOf(body: any, receivedAt: number): Incident {
  const d = body?.data || body || {};
  const a = d.attributes || {};
  const id = /^\d+$/.test(String(d.id ?? "")) ? String(d.id) : "";
  const started = Date.parse(a.started_at || "");
  return {
    id,
    startedAt: Number.isFinite(started) ? Math.min(started, receivedAt) : receivedAt,
    name: String(a.name || a.cause || body?.name || ""),
    cause: String(a.cause || ""),
  };
}

export function isResolvedEvent(body: any): boolean {
  const a = body?.data?.attributes || body?.attributes || {};
  const status = String(a.status || body?.status || "").toLowerCase();
  return Boolean(a.resolved_at) || status === "resolved" || status === "acknowledged";
}

async function api(method: string, path: string, body?: unknown): Promise<Response | null> {
  const tok = rt.env.BETTERSTACK_API_TOKEN;
  if (!tok) return null;
  try {
    return await rt.fetch(`${UPTIME}${path}`, {
      method,
      headers: { Authorization: `Bearer ${tok}`, "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: timeout(10_000),
    });
  } catch {
    return null;
  }
}

async function postIncident(id: string, verb: "acknowledge" | "resolve", body: Record<string, string>): Promise<boolean> {
  for (const v of ["v3", "v2"]) {
    const r = await api("POST", `/${v}/incidents/${id}/${verb}`, body);
    if (r?.ok) return true;
  }
  return false;
}

export const ackIncident = (id: string, by = BY) => postIncident(id, "acknowledge", { acknowledged_by: by });
export const resolveIncident = (id: string, by = BY) => postIncident(id, "resolve", { resolved_by: by });

// A note on the incident timeline. Best effort: the resolve is what stops the call.
export async function commentIncident(id: string, content: string): Promise<boolean> {
  const r = await api("POST", `/v2/incidents/${id}/comments`, { content });
  return Boolean(r?.ok);
}

// Page people (used for blind spots: nothing is broken yet, but we went blind).
export async function createIncident(name: string, summary: string): Promise<boolean> {
  const r = await api("POST", "/v3/incidents", {
    requester_email: rt.env.BETTERSTACK_REQUESTER_EMAIL || "seraphine@finverified.ai",
    name,
    summary,
    call: true,
    sms: true,
    email: true,
  });
  return Boolean(r?.ok);
}

async function pages(path: string, max = 5): Promise<any[]> {
  const out: any[] = [];
  let next: string | null = path;
  for (let i = 0; next && i < max; i++) {
    const r = await api("GET", next.replace(UPTIME, ""));
    if (!r?.ok) break;
    const j: any = await r.json();
    out.push(...(j.data || []));
    next = j.pagination?.next || null;
  }
  return out;
}

export type IncidentRow = {
  id: string; name: string; startedAt: number; ackedAt?: number; resolvedAt?: number;
  ackedBy: string; resolvedBy: string;
};

export async function listIncidents(fromIso: string, toIso: string): Promise<IncidentRow[]> {
  const rows = await pages(`/v3/incidents?from=${fromIso}&to=${toIso}&per_page=50`);
  return rows.map((x: any) => {
    const a = x.attributes || {};
    const t = (s: string | null) => (s ? Date.parse(s) : undefined);
    return {
      id: String(x.id), name: String(a.name || a.cause || ""), startedAt: Date.parse(a.started_at),
      ackedAt: t(a.acknowledged_at), resolvedAt: t(a.resolved_at),
      ackedBy: String(a.acknowledged_by || ""), resolvedBy: String(a.resolved_by || ""),
    };
  });
}

export type Uptime = { name: string; availability: number | null };

export async function monitorUptime(fromDate: string, toDate: string): Promise<Uptime[]> {
  const monitors = await pages("/v2/monitors?per_page=50");
  const out: Uptime[] = [];
  for (const m of monitors) {
    const name = String(m.attributes?.pronounceable_name || m.attributes?.url || m.id);
    const r = await api("GET", `/v2/monitors/${m.id}/sla?from=${fromDate}&to=${toDate}`);
    const j: any = r?.ok ? await r.json() : null;
    out.push({ name, availability: j?.data?.attributes?.availability ?? null });
  }
  return out;
}
