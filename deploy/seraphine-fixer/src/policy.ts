// What Seraphine may do on her own (safe list), what she never does
// (never-list), and the per-service rate limit. The never-list is enforced
// in code: every Railway and Cloudflare write goes through the checks below,
// and anything outside the safe list throws before a request is sent.

import { MAX_ACTIONS_PER_HOUR, PRODUCTION_ENVS } from "./config";
import { boot, rt } from "./runtime";

export const SAFE_LIST = [
  "Restart a down or crashed service.",
  "Roll back a release under 2 hours old (never the API: DB migrations make that unsafe).",
  "Put back a website DNS address record (A/AAAA/CNAME) to the exact copy she saw working.",
  "Acknowledge and resolve a Better Stack incident after a fix she verified with 2 healthy checks.",
  "Post to #alerts, update her own thread, open or update a Linear Bug.",
  "Stop a STAGING service during the monthly drill (never production).",
];

export const NEVER_LIST = [
  "code (no commits, no pushes, no merges)",
  "databases (no queries that write, no migrations, no data edits)",
  "environment variables and secrets",
  "IAM, users and access",
  "money (plans, billing, payments)",
  "deleting anything (services, volumes, DNS records)",
  "email DNS records (MX/TXT)",
];

export class NeverListError extends Error {
  constructor(what: string) {
    super(`Blocked by the never-list: ${what}. Seraphine diagnoses this and hands the exact fix to a human.`);
    this.name = "NeverListError";
  }
}

const RAILWAY_MUTATIONS = new Set(["deploymentRestart", "deploymentRollback"]);
const DRILL_MUTATIONS = new Set(["deploymentStop"]);

// Names of the fields a GraphQL mutation calls, e.g. ["deploymentRestart"].
export function mutationFields(query: string): string[] {
  if (!/^\s*mutation\b/.test(query)) return [];
  const body = query.slice(query.indexOf("{") + 1);
  return [...body.matchAll(/\b([A-Za-z_]\w*)\s*[({]/g)].map((m) => m[1]);
}

// Railway: only restart/rollback, plus stop for a staging drill.
export function checkRailway(query: string, opts: { drillEnv?: string } = {}) {
  for (const f of mutationFields(query)) {
    if (RAILWAY_MUTATIONS.has(f)) continue;
    if (DRILL_MUTATIONS.has(f) && opts.drillEnv && !PRODUCTION_ENVS.has(opts.drillEnv)) continue;
    throw new NeverListError(`Railway "${f}"`);
  }
}

export const REPAIRABLE_TYPES = ["A", "AAAA", "CNAME"];

// Cloudflare: read anything; write only website address records; never delete.
export function checkCloudflare(method: string, path: string, body?: string) {
  const m = method.toUpperCase();
  if (m === "GET") return;
  if (m === "DELETE") throw new NeverListError("deleting a DNS record");
  if (!/^\/zones\/[\w-]+\/dns_records(\/[\w-]+)?$/.test(path)) throw new NeverListError(`Cloudflare ${m} ${path}`);
  const type = body ? JSON.parse(body).type : undefined;
  if (type !== undefined && !REPAIRABLE_TYPES.includes(type)) throw new NeverListError(`changing a ${type} record`);
}

// ---- Rate limit: max 2 actions per service per hour; only 1 in her first
// hour after she herself restarts, so a crash loop of hers can never reset it.
const actionLog = new Map<string, number[]>();

export function canAct(serviceId: string): boolean {
  const now = rt.now();
  const recent = (actionLog.get(serviceId) || []).filter((ts) => now - ts < 3_600_000);
  actionLog.set(serviceId, recent);
  const limit = now - boot.at < 3_600_000 ? 1 : MAX_ACTIONS_PER_HOUR;
  return recent.length < limit;
}

export function record(serviceId: string) {
  if (!actionLog.has(serviceId)) actionLog.set(serviceId, []);
  actionLog.get(serviceId)!.push(rt.now());
}

export function resetLimits() {
  actionLog.clear();
}
