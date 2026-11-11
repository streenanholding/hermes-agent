// Seraphine Auto-Fixer — Head of IT & Services
// Better Stack calls this when a monitor goes down. Seraphine first checks for
// herself that the site is really down (2 checks, 15s apart). If it is, she
// restarts the broken Railway service. If it is still down 2 minutes later and
// the newest deploy is recent, she rolls back to the previous deploy. If the
// app is fine but the site's DNS record is broken, she puts the record back in
// Cloudflare. Then she stops and leaves the rest to humans (Better Stack keeps
// calling Rick).
//
// TIER 1 (she does it alone): restart, roll back a recent bad release, put back
// a broken website DNS record.
// She never touches code, databases, variables, users or money.
// DNS: she only puts back a website address record (A/AAAA/CNAME) for one of
// our sites to the exact version she saw working. She never deletes records
// and never touches email (MX/TXT) records.
// The API is restart-only (DB migrations make code rollback unsafe).
// Max 2 actions per service per hour (only 1 in her first hour after she
// herself restarts, so a crash loop of hers can never reset the limit).
// Max 1 DNS repair per site per hour.
//
// The webhook URL carries no secret: nothing happens unless Seraphine's own
// checks confirm the site is down, so a fake call can't cause harm.
//
// History:
// Oct 15 2026: alerts matched to a service by EXACT hostname; unknown hosts
//   are reported "humans needed", never guessed. Sandbox added.
// Oct 16 2026: Playwright/journey alerts: probe key pages twice; fix only
//   real 5xx/unreachable; otherwise report and do NOT touch production.
// Oct 16 2026: DNS alerts never restart; acknowledge only what she saw up.
// Oct 16 2026: walkthrough + Academy are full repair targets.
// Oct 16 2026: PATROL every 5 min; daily 8 AM ET report.
// Oct 16 2026: Slack posts retry once, never log the Slack link.
// Oct 17 2026: DNS guard before ANY restart (Google + Cloudflare DNS).
// Oct 17 2026 (v2, Head of IT):
//   - AGENT PLATFORM: LiteLLM gateway (web check) and Sol, Carly, Seraphine's
//     Slack brain and the agent database (Railway status check). If one has
//     CRASHED she restarts it (never rolls back). Needs RAILWAY_TOKEN_AGENTS.
//   - HEARTBEAT: every patrol pings Better Stack. If she ever stops
//     patrolling (stuck or dead), Better Stack calls Rick.
//   - BOOT GUARD: only 1 fix per service in her first hour after a restart.
//   - EXPIRY: daily report warns 30 days before a security certificate ends
//     and 45 days before the finverified.ai domain registration ends.
//   - BUILD WATCH: if a service's newest release failed to build (the old
//     version keeps running), she says so once a day.
// Oct 17 2026 (v3, she fixes DNS too):
//   - DNS REPAIR: finverified.ai DNS is on Cloudflare now. Every 30 min, while
//     a site works, she saves a copy of its Cloudflare address record. If the
//     site later breaks because that record was deleted or changed, she puts
//     the saved copy back, then re-checks. If Cloudflare still has the right
//     record (internet catching up), she says there's nothing to change.
//     Needs CLOUDFLARE_API_TOKEN.
//   - CERT GUARD: a broken security certificate is never "fixed" by a restart.
//
// Variables (set in Railway, never in code):
//   FIXER_KEY                 protects the /test page
//   RAILWAY_TOKEN_WEBSITE     Railway project token: finverified-website / production
//   RAILWAY_TOKEN_APP         Railway project token: finverified-app / production
//   RAILWAY_TOKEN_SANDBOX     Railway project token: finverified-sandbox / sandbox
//   RAILWAY_TOKEN_WALKTHROUGH Railway project token: finverified-walkthrough / production
//   RAILWAY_TOKEN_ACADEMY     Railway project token: finverified-launch-lab / production
//   RAILWAY_TOKEN_AGENTS      Railway project token: agent-platform / production
//   CLOUDFLARE_API_TOKEN      Cloudflare token: Zone Read + DNS Edit on finverified.ai only
//   CLOUDFLARE_ZONE_ID        optional, found automatically from the token
//   SLACK_WEBHOOK_URL         optional, Slack incoming webhook for #alerts
//   BETTERSTACK_API_TOKEN     optional, lets her acknowledge DNS blips she confirmed are up
//   BETTERSTACK_HEARTBEAT_URL optional, pinged after every patrol

const RAILWAY_API = "https://backboard.railway.com/graphql/v2";
const MAX_ACTIONS_PER_HOUR = 2;
const ROLLBACK_WINDOW_MIN = 120;
const VERIFY_AFTER_MS = 120_000;
const BOOT = Date.now();

type Target = {
  name: string;
  projectId: string;
  environmentId: string;
  serviceId: string;
  tokenVar: string;
  healthUrl: string;
  allowRollback: boolean;
  match: string[]; // exact hostnames only
  okBelow500?: boolean; // any answer under 500 counts as "up" (used where the exact health path is unverified)
};

const AGENT_PROJECT = "b5592ad0-6a97-4d8c-b7a4-bf8a2f285f47";
const AGENT_ENV = "150daae5-a2f0-4c52-894e-84f60fca8fde";

const TARGETS: Target[] = [
  {
    name: "Platform API (api.finverified.ai)",
    projectId: "b00697ce-eec6-4268-9080-b70a8ee85176",
    environmentId: "f4709c5c-1d75-4e30-b02f-f06059512cb3",
    serviceId: "f1196a49-9cf1-467c-992c-c0ad3ebef78a",
    tokenVar: "RAILWAY_TOKEN_APP",
    healthUrl: "https://api.finverified.ai/health",
    allowRollback: false,
    match: ["api.finverified.ai", "finverified-app-production.up.railway.app"],
  },
  {
    name: "Platform web (app.finverified.ai)",
    projectId: "b00697ce-eec6-4268-9080-b70a8ee85176",
    environmentId: "f4709c5c-1d75-4e30-b02f-f06059512cb3",
    serviceId: "46889cf7-00b4-4040-9575-6f940aaf33ec",
    tokenVar: "RAILWAY_TOKEN_APP",
    healthUrl: "https://app.finverified.ai",
    allowRollback: true,
    match: ["app.finverified.ai", "finverified-web-test-production.up.railway.app"],
  },
  {
    name: "Advisor Sandbox (sandbox.finverified.ai)",
    projectId: "77c5be8f-a4c8-409a-9323-ef25398f00af",
    environmentId: "b4956758-7c25-42ef-8def-3c889089f958",
    serviceId: "808545a2-88dd-457f-a656-508e61ef4c90",
    tokenVar: "RAILWAY_TOKEN_SANDBOX",
    healthUrl: "https://sandbox.finverified.ai",
    allowRollback: true,
    match: ["sandbox.finverified.ai", "sandbox-web-sandbox-0726.up.railway.app"],
  },
  {
    name: "Advisor walkthrough (walkthrough.finverified.ai)",
    projectId: "2326ad7a-d644-45f1-b602-07dc7288db48",
    environmentId: "3a4ea6cb-df98-479e-8af0-e0cb44d3ee8c",
    serviceId: "686afe20-b6b2-4bb0-a2d9-c19e7e822d1a",
    tokenVar: "RAILWAY_TOKEN_WALKTHROUGH",
    healthUrl: "https://walkthrough.finverified.ai",
    allowRollback: true,
    match: ["walkthrough.finverified.ai", "walkthrough-production-b080.up.railway.app"],
  },
  {
    name: "Partner Academy (academy.finverified.ai)",
    projectId: "ff743c4b-d40c-4a4c-b581-3abc4614b666",
    environmentId: "23dac866-c961-4a3f-887a-e0dee9330bf0",
    serviceId: "1d4dc733-28f3-4fb7-9e74-8cb874958e06",
    tokenVar: "RAILWAY_TOKEN_ACADEMY",
    healthUrl: "https://academy.finverified.ai/health",
    allowRollback: true,
    match: ["academy.finverified.ai", "finverified-academy.up.railway.app"],
  },
  {
    name: "Website (finverified.ai)",
    projectId: "b29288a0-8c0a-422e-a912-933ca840889b",
    environmentId: "4fb518a3-93a6-4e27-90dd-481bea495577",
    serviceId: "258eba89-0f98-43ec-b632-e5fd261150a8",
    tokenVar: "RAILWAY_TOKEN_WEBSITE",
    healthUrl: "https://finverified.ai",
    allowRollback: true,
    match: ["www.finverified.ai", "finverified.ai", "finverified-website-production.up.railway.app"],
  },
  {
    name: "AI gateway (LiteLLM — every agent's brain goes through it)",
    projectId: AGENT_PROJECT,
    environmentId: AGENT_ENV,
    serviceId: "9cbc81de-0ada-491e-8e47-3c764dbc6bfc",
    tokenVar: "RAILWAY_TOKEN_AGENTS",
    healthUrl: "https://litellm-gateway-production-774e.up.railway.app/health/liveliness",
    allowRollback: false,
    match: ["litellm-gateway-production-774e.up.railway.app"],
    okBelow500: true,
  },
];

// Services with no web address (they dial out to Slack/Telegram). Checked by
// asking Railway whether the running copy has CRASHED. Restart only.
type StatusTarget = { name: string; serviceId: string };
const STATUS_TARGETS: StatusTarget[] = [
  { name: "Sol (CFO agent)", serviceId: "d37c0687-9282-49d1-abab-56103c1a8e70" },
  { name: "Carly (Chief of Staff agent)", serviceId: "c6055e21-cb61-469c-b9a2-1a9f7b6b7ff5" },
  { name: "Seraphine's Slack brain (hermes-seraphine)", serviceId: "087ecb34-8f2f-49f0-a5aa-1cda82b39a1f" },
  { name: "Agent database (pgvector-db)", serviceId: "6e7feead-083a-4f0f-9cbf-d630b60c542e" },
];
const asTarget = (s: StatusTarget): Target => ({
  name: s.name, projectId: AGENT_PROJECT, environmentId: AGENT_ENV, serviceId: s.serviceId,
  tokenVar: "RAILWAY_TOKEN_AGENTS", healthUrl: "", allowRollback: false, match: [],
});

const WEBSITE_NAME = "Website (finverified.ai)";
const WATCHED_SUFFIXES = ["finverified.ai", "up.railway.app"];

const actionLog = new Map<string, number[]>(); // serviceId -> action timestamps
const busy = new Set<string>(); // serviceIds with a fix in progress

// Hostnames in the alert that belong to us. Email addresses (rick@finverified.ai) are skipped.
function hostsIn(text: string): string[] {
  const t = text.toLowerCase();
  const out = new Set<string>();
  const re = /(?<![@\w.-])((?:[a-z0-9-]+\.)+[a-z]{2,})(?![\w-])/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(t))) {
    const h = m[1];
    if (WATCHED_SUFFIXES.some((s) => h === s || h.endsWith("." + s))) out.add(h);
  }
  return [...out];
}

type Resolution = { target?: Target; hosts: string[]; unknown: string[] };

function resolveTarget(text: string): Resolution {
  const hosts = hostsIn(text).filter((h) => h !== "seraphine-fixer-production.up.railway.app");
  const unknown = hosts.filter((h) => !TARGETS.some((x) => x.match.includes(h)));
  if (unknown.length) return { hosts, unknown };
  const matched = TARGETS.filter((x) => x.match.some((m) => hosts.includes(m)));
  const specific = matched.filter((x) => x.name !== WEBSITE_NAME);
  return { target: specific[0] || matched[0], hosts, unknown };
}

async function gql(token: string, query: string, variables: Record<string, unknown>) {
  const res = await fetch(RAILWAY_API, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Project-Access-Token": token },
    body: JSON.stringify({ query, variables }),
  });
  const json: any = await res.json();
  if (json.errors) throw new Error(JSON.stringify(json.errors));
  return json.data;
}

async function listDeployments(t: Target, token: string) {
  const data = await gql(
    token,
    `query($input: DeploymentListInput!) {
       deployments(first: 10, input: $input) { edges { node { id status createdAt } } }
     }`,
    { input: { projectId: t.projectId, environmentId: t.environmentId, serviceId: t.serviceId } },
  );
  const nodes = data.deployments.edges.map((e: any) => e.node);
  return nodes.sort(
    (a: any, b: any) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
  );
}

type Plan = { action: "restart" | "rollback" | "none"; deploymentId?: string; reason: string };

const IN_PROGRESS = ["BUILDING", "DEPLOYING", "INITIALIZING", "QUEUED", "WAITING"];

function currentOf(deps: any[]) {
  return deps.find((d) => d.status === "SUCCESS" || d.status === "CRASHED");
}

// Step 1: always restart first. A restart can never undo a fix.
function planRestart(deps: any[]): Plan {
  if (deps.length && IN_PROGRESS.includes(deps[0].status)) {
    return { action: "none", reason: `A deploy is already in progress (${deps[0].status}).` };
  }
  const current = currentOf(deps);
  if (!current) return { action: "none", reason: "No running or crashed deployment found." };
  return { action: "restart", deploymentId: current.id, reason: `Restarting (status was ${current.status}).` };
}

// Step 2: only if still down after the restart, and only if the newest deploy is recent.
function planRollback(t: Target, deps: any[]): Plan {
  if (!t.allowRollback) return { action: "none", reason: "Rollback is turned off for this service." };
  if (deps.length && IN_PROGRESS.includes(deps[0].status)) {
    return { action: "none", reason: `A deploy is in progress (${deps[0].status}).` };
  }
  const current = currentOf(deps);
  if (!current) return { action: "none", reason: "No current deployment found." };
  const ageMin = (Date.now() - new Date(current.createdAt).getTime()) / 60000;
  if (ageMin >= ROLLBACK_WINDOW_MIN) {
    return { action: "none", reason: `Newest deploy is ${Math.round(ageMin)} min old, so a bad deploy is unlikely. Not rolling back.` };
  }
  const idx = deps.indexOf(current);
  const previous = deps.slice(idx + 1).find((d) => d.status === "REMOVED" || d.status === "SUCCESS");
  if (!previous) return { action: "none", reason: "No earlier deploy to roll back to." };
  return {
    action: "rollback",
    deploymentId: previous.id,
    reason: `Restart didn't fix it and the newest deploy is ${Math.round(ageMin)} min old, so rolling back to the previous deploy. Check what that newest deploy changed before re-deploying it.`,
  };
}

async function act(token: string, plan: Plan) {
  if (plan.action === "restart") {
    await gql(token, `mutation($id: String!) { deploymentRestart(id: $id) }`, { id: plan.deploymentId });
  } else if (plan.action === "rollback") {
    await gql(token, `mutation($id: String!) { deploymentRollback(id: $id) }`, { id: plan.deploymentId });
  }
}

// Posts to #alerts. Retries once. Never logs the Slack link itself.
async function slack(text: string) {
  console.log(text);
  const url = Bun.env.SLACK_WEBHOOK_URL;
  if (!url) return;
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
        signal: AbortSignal.timeout(10_000),
      });
      if (r.ok) return;
      console.error(`Slack post failed (attempt ${attempt}): HTTP ${r.status}`);
    } catch (e: any) {
      console.error(`Slack post failed (attempt ${attempt}): ${String(e?.code || e?.name || "network error")}`);
    }
    if (attempt === 1) await Bun.sleep(2_000);
  }
}

const CERT_ERROR = "certificate error";

// Tells a broken security certificate apart from a site that doesn't answer.
function failDetail(e: any): string {
  const s = `${e?.code || ""} ${e?.message || ""} ${e?.cause?.code || ""} ${e?.cause?.message || ""}`;
  return /CERT|certificate|TLS|SSL|self.signed|altname/i.test(s) ? CERT_ERROR : "unreachable";
}

async function urlUp(u: string): Promise<{ up: boolean; detail: string }> {
  try {
    const res = await fetch(u, { redirect: "follow", signal: AbortSignal.timeout(20_000) });
    return { up: res.ok, detail: `HTTP ${res.status}` };
  } catch (e: any) {
    return { up: false, detail: failDetail(e) };
  }
}

async function urlUpLoose(u: string): Promise<{ up: boolean; detail: string }> {
  try {
    const res = await fetch(u, { redirect: "follow", signal: AbortSignal.timeout(20_000) });
    return { up: res.status < 500, detail: `HTTP ${res.status}` };
  } catch (e: any) {
    return { up: false, detail: failDetail(e) };
  }
}

const isUp = (t: Target) => (t.okBelow500 ? urlUpLoose(t.healthUrl) : urlUp(t.healthUrl));

// Seraphine's own confirmation: must fail twice, 15 seconds apart.
async function confirmDown(t: Target): Promise<{ down: boolean; detail: string }> {
  const a = await isUp(t);
  if (a.up) return { down: false, detail: a.detail };
  await Bun.sleep(15_000);
  const b = await isUp(t);
  return { down: !b.up, detail: b.detail };
}

async function confirmDownWith(check: () => Promise<{ up: boolean; detail: string }>) {
  const a = await check();
  if (a.up) return { down: false, detail: a.detail };
  await Bun.sleep(15_000);
  const b = await check();
  return { down: !b.up, detail: b.detail };
}

// In her first hour after she herself (re)starts she gets only 1 fix per
// service, so a crash loop of the fixer can never reset the safety limit.
function canAct(serviceId: string): boolean {
  const now = Date.now();
  const recent = (actionLog.get(serviceId) || []).filter((ts) => now - ts < 3_600_000);
  actionLog.set(serviceId, recent);
  const limit = now - BOOT < 3_600_000 ? 1 : MAX_ACTIONS_PER_HOUR;
  return recent.length < limit;
}

function record(serviceId: string) {
  if (!actionLog.has(serviceId)) actionLog.set(serviceId, []);
  actionLog.get(serviceId)!.push(Date.now());
}

function isResolvedEvent(body: any): boolean {
  const a = body?.data?.attributes || body?.attributes || {};
  const status = String(a.status || body?.status || "").toLowerCase();
  return Boolean(a.resolved_at) || status === "resolved" || status === "acknowledged";
}

const STILL_DOWN_HINT =
  "If the service logs show the app running, check that the domain's target port matches the port the app listens on (Sandbox outage, Oct 12–13, was a 3000 vs 8080 mismatch).";

// DNS guard used before ANY restart: if public DNS has no address for the
// site, it's a DNS problem and a restart can't help.
const dnsGuardNote = new Map<string, number>();
async function dnsBroken(t: Target, checkUrl?: string): Promise<string | null> {
  const host = new URL(checkUrl || t.healthUrl).hostname;
  if (host.endsWith(".up.railway.app")) return null;
  const dns = await publicDns(host);
  return /EMPTY/.test(dns) ? `${host} — public DNS: ${dns}` : null;
}

// ---- DNS repair (Cloudflare) ----
// While a site works she saves a copy of its Cloudflare address record. If the
// site later breaks because that record was deleted or changed, she puts the
// saved copy back. She never deletes records and never touches MX/TXT.
const CF_API = "https://api.cloudflare.com/client/v4";
const CF_ZONE = "finverified.ai";
const REPAIRABLE_TYPES = ["A", "AAAA", "CNAME"];
const SNAPSHOT_EVERY_MS = 30 * 60_000;
type CfRecord = { id?: string; type: string; name: string; content: string; proxied: boolean; ttl: number };
const goodDns = new Map<string, CfRecord[]>(); // host -> records last seen while the site worked
const goodDnsAt = new Map<string, number>();
const dnsFixLog = new Map<string, number>(); // host -> last repair time
let cfZoneId = "";

const inZone = (h: string) => h === CF_ZONE || h.endsWith("." + CF_ZONE);

async function cf(path: string, init: { method?: string; body?: string } = {}) {
  const tok = Bun.env.CLOUDFLARE_API_TOKEN;
  if (!tok) throw new Error("CLOUDFLARE_API_TOKEN is not set");
  const r = await fetch(CF_API + path, {
    method: init.method || "GET",
    body: init.body,
    headers: { Authorization: `Bearer ${tok}`, "Content-Type": "application/json" },
    signal: AbortSignal.timeout(15_000),
  });
  const j: any = await r.json();
  if (!j.success) throw new Error(`Cloudflare said: ${JSON.stringify(j.errors || r.status).slice(0, 200)}`);
  return j;
}

async function zoneId(): Promise<string> {
  if (cfZoneId) return cfZoneId;
  if (Bun.env.CLOUDFLARE_ZONE_ID) return (cfZoneId = Bun.env.CLOUDFLARE_ZONE_ID);
  const j = await cf(`/zones?name=${CF_ZONE}`);
  if (!j.result?.length) throw new Error("the Cloudflare key can't see the finverified.ai zone");
  return (cfZoneId = j.result[0].id);
}

async function cfRecords(host: string): Promise<CfRecord[]> {
  const z = await zoneId();
  const j = await cf(`/zones/${z}/dns_records?name=${encodeURIComponent(host)}&per_page=100`);
  return (j.result || [])
    .filter((x: any) => REPAIRABLE_TYPES.includes(x.type))
    .map((x: any) => ({ id: x.id, type: x.type, name: x.name, content: x.content, proxied: Boolean(x.proxied), ttl: x.ttl }));
}

const sameRec = (a: CfRecord, b: CfRecord) =>
  a.type === b.type && a.content.toLowerCase() === b.content.toLowerCase() && a.proxied === b.proxied;

function describe(recs: CfRecord[]): string {
  return recs.length ? recs.map((r) => `${r.type} → ${r.content}${r.proxied ? " (orange cloud)" : ""}`).join(", ") : "no address record";
}

// Called while a site is working: save its record as the known-good copy.
async function snapshotDns(host: string) {
  if (!Bun.env.CLOUDFLARE_API_TOKEN || !inZone(host)) return;
  if (Date.now() - (goodDnsAt.get(host) || 0) < SNAPSHOT_EVERY_MS) return;
  try {
    const recs = await cfRecords(host);
    if (recs.length) {
      goodDns.set(host, recs);
      goodDnsAt.set(host, Date.now());
    }
  } catch (e) {
    console.error("dns snapshot error", host, e);
  }
}

async function repairDns(host: string): Promise<{ changed: boolean; msg: string }> {
  if (!inZone(host)) return { changed: false, msg: `${host} isn't one of our Cloudflare sites.` };
  if (!Bun.env.CLOUDFLARE_API_TOKEN) {
    return { changed: false, msg: "I can't repair DNS yet: CLOUDFLARE_API_TOKEN is not set in my variables. Humans needed." };
  }
  const key = "dnsfix:" + host;
  if (busy.has(key)) return { changed: false, msg: "I'm already repairing it." };
  busy.add(key);
  try {
    const now = await cfRecords(host);
    const good = goodDns.get(host);
    if (!good?.length) {
      return { changed: false, msg: `I don't have a saved working copy of the ${host} record yet, so I won't guess. Cloudflare has: ${describe(now)}. Humans needed.` };
    }
    const missing = good.filter((g) => !now.some((n) => sameRec(g, n)));
    if (!missing.length) {
      return { changed: false, msg: `Cloudflare still has the correct ${host} record (${describe(now)}), so nothing is broken on our side — it's the internet catching up or a DNS provider hiccup. Nothing to change; it clears on its own.` };
    }
    const last = dnsFixLog.get(host) || 0;
    if (Date.now() - last < 3_600_000) {
      return { changed: false, msg: `I already repaired ${host} DNS within the last hour and it broke again. Not repeating — something or someone keeps changing it. Humans needed.` };
    }
    dnsFixLog.set(host, Date.now());
    const z = await zoneId();
    const done: string[] = [];
    for (const g of missing) {
      const sameType = now.find((n) => n.type === g.type);
      const clash = now.find((n) => n.type !== g.type && (g.type === "CNAME" || n.type === "CNAME"));
      if (sameType?.id) {
        await cf(`/zones/${z}/dns_records/${sameType.id}`, {
          method: "PATCH",
          body: JSON.stringify({ content: g.content, proxied: g.proxied, ttl: g.ttl }),
        });
        done.push(`put ${g.type} ${host} back to ${g.content} (it had been changed to ${sameType.content})`);
      } else if (clash) {
        const pre = done.length ? `I fixed part of it (${done.join("; ")}), but ` : "";
        return {
          changed: done.length > 0,
          msg: `${pre}${host} now has a ${clash.type} record where the working ${g.type} record used to be. I don't delete records. Humans needed. The working version was: ${g.type} → ${g.content}${g.proxied ? " (orange cloud)" : ""}.`,
        };
      } else {
        await cf(`/zones/${z}/dns_records`, {
          method: "POST",
          body: JSON.stringify({ type: g.type, name: host, content: g.content, proxied: g.proxied, ttl: g.ttl }),
        });
        done.push(`re-created the missing ${g.type} record ${host} → ${g.content}`);
      }
    }
    await Bun.sleep(60_000);
    const after = await urlUp(checkUrlFor(host));
    const dnsNow = await publicDns(host);
    return {
      changed: true,
      msg: `🛠️ I repaired it in Cloudflare: ${done.join("; ")}. ${after.up ? `✅ ${host} is loading again (${after.detail}).` : `Not loading yet (${after.detail}; public DNS: ${dnsNow}) — DNS changes can take a few minutes. Better Stack will close the incident when it's back.`}`,
    };
  } catch (e: any) {
    console.error(e);
    return { changed: false, msg: `My DNS repair failed: ${String(e?.message || e).slice(0, 200)}. Humans needed.` };
  } finally {
    busy.delete(key);
  }
}

const certNote = new Map<string, number>();
const CERT_HINT =
  "A restart can't fix a certificate, so I did NOT restart. Right after a DNS move this clears on its own within ~15 min. If it lasts longer, check Cloudflare → SSL/TLS is set to \"Full\", and the domain shows a green check in Railway.";

async function runFix(t: Target, token: string, checkUrl?: string) {
  const check = () => (checkUrl ? urlUp(checkUrl) : isUp(t));
  busy.add(t.serviceId);
  try {
    // Step 0: confirm it's really down
    const c0 = await confirmDownWith(check);
    if (!c0.down) {
      console.log(`Alert for ${t.name} but it is up (${c0.detail}). No action.`);
      return;
    }

    // Step 0a: certificate guard — a restart never fixes a certificate
    if (c0.detail === CERT_ERROR) {
      const last = certNote.get(t.serviceId) || 0;
      if (Date.now() - last > 3_600_000) {
        certNote.set(t.serviceId, Date.now());
        await slack(`🔒 Seraphine: ${t.name} has a security certificate (https lock) problem. ${CERT_HINT}`);
      }
      return;
    }

    // Step 0b: DNS guard — never restart for a DNS problem; repair the record instead
    const dnsIssue = await dnsBroken(t, checkUrl);
    if (dnsIssue) {
      const host = new URL(checkUrl || t.healthUrl).hostname;
      const fix = await repairDns(host);
      const last = dnsGuardNote.get(t.serviceId) || 0;
      if (fix.changed || Date.now() - last > 3_600_000) {
        dnsGuardNote.set(t.serviceId, Date.now());
        await slack(`🌐 Seraphine: ${t.name} is unreachable because its DNS address is missing (${dnsIssue}). Not an app problem, so no restart. ${fix.msg}`);
      }
      return;
    }

    // Step 1: restart
    const deps1 = await listDeployments(t, token);
    const p1 = planRestart(deps1);
    if (p1.action === "none") {
      await slack(`🚨 Seraphine: ${t.name} is down (${c0.detail}). ${p1.reason} No action taken. Humans needed. ${STILL_DOWN_HINT}`);
      return;
    }
    if (!canAct(t.serviceId)) {
      await slack(`🛑 Seraphine: ${t.name} is down again but I've used my fixes for this hour. Stopping. Humans needed.`);
      return;
    }
    await act(token, p1);
    record(t.serviceId);
    await slack(`🔧 Seraphine: ${t.name} went down (${c0.detail}). ${p1.reason}`);

    await Bun.sleep(VERIFY_AFTER_MS);
    const c1 = await check();
    if (c1.up) {
      await slack(`✅ Seraphine: ${t.name} is back up after a restart (${c1.detail}).`);
      return;
    }

    // Step 2: rollback (only if allowed and recent deploy)
    const deps2 = await listDeployments(t, token);
    const p2 = planRollback(t, deps2);
    if (p2.action === "none" || !canAct(t.serviceId)) {
      await slack(`🚨 Seraphine: ${t.name} still down after restart (${c1.detail}). ${p2.reason} Humans needed — Better Stack is calling. ${STILL_DOWN_HINT}`);
      return;
    }
    await act(token, p2);
    record(t.serviceId);
    await slack(`⏪ Seraphine: ${t.name} ${p2.reason}`);

    await Bun.sleep(VERIFY_AFTER_MS);
    const c2 = await check();
    await slack(
      c2.up
        ? `✅ Seraphine: ${t.name} is back up after rollback (${c2.detail}). Review the rolled-back deploy before re-deploying.`
        : `🚨 Seraphine: ${t.name} still down after restart and rollback (${c2.detail}). Stopping. Humans needed. ${STILL_DOWN_HINT}`,
    );
  } catch (e: any) {
    console.error(e);
    const msg = String(e?.message || e);
    const hint = /Not Authorized/i.test(msg) ? ` ${t.tokenVar} is expired or wrong — make a new Railway project token and paste it into my variables.` : "";
    await slack(`⚠️ Seraphine fixer error on ${t.name}: ${msg.slice(0, 300)}${hint}`);
  } finally {
    busy.delete(t.serviceId);
  }
}

// Known service but no token for it: still check it and say so loudly.
const noTokenNote = new Map<string, number>();
async function reportNoToken(t: Target) {
  const c = await confirmDown(t);
  if (!c.down) {
    console.log(`Alert for ${t.name} but it is up (${c.detail}). No action.`);
    return;
  }
  const last = noTokenNote.get(t.serviceId) || 0;
  if (Date.now() - last < 3_600_000) return;
  noTokenNote.set(t.serviceId, Date.now());
  await slack(`🚨 Seraphine: ${t.name} is DOWN (${c.detail}). I can't act on it: ${t.tokenVar} is not set. Humans needed. ${STILL_DOWN_HINT}`);
}

// Host we don't manage: check it ourselves and say so loudly. Never guess another service.
async function reportUnknown(hosts: string[]) {
  const results = await Promise.all(hosts.map(async (h) => ({ h, r: await urlUp(`https://${h}`) })));
  const down = results.filter((x) => !x.r.up);
  if (!down.length) {
    console.log(`Alert for unmanaged host(s) ${hosts.join(", ")} but they are up. No action.`);
    return;
  }
  await slack(
    `🚨 Seraphine: alert for a site I don't manage: ${down.map((x) => `${x.h} (${x.r.detail})`).join(", ")}. No action taken. Humans needed.`,
  );
}

// ---- Agent platform: services with no web address ----
const buildNote = new Map<string, string>(); // serviceId -> day already reported

async function checkStatusTarget(s: StatusTarget) {
  const t = asTarget(s);
  if (busy.has(t.serviceId)) return;
  const token = Bun.env[t.tokenVar];
  if (!token) return; // reported once a day by the self-check
  const deps = await listDeployments(t, token);
  if (!deps.length) return;

  // Newest release failed to build: the old one keeps running. Say so once a day.
  if (deps[0].status === "FAILED") {
    const day = new Date().toISOString().slice(0, 10);
    if (buildNote.get(t.serviceId) !== day) {
      buildNote.set(t.serviceId, day);
      await slack(`🧱 Seraphine: the newest release of ${t.name} failed to build. The previous version is still running, so nothing is down — but that change never went live. Humans: check the build log in Railway.`);
    }
  }

  const cur = currentOf(deps);
  if (!cur || cur.status !== "CRASHED") return;

  busy.add(t.serviceId);
  try {
    // Confirm: still crashed 15 seconds later
    await Bun.sleep(15_000);
    const again = currentOf(await listDeployments(t, token));
    if (!again || again.status !== "CRASHED") return;
    if (!canAct(t.serviceId)) {
      await slack(`🛑 Seraphine: ${t.name} has crashed again but I've used my fixes for this hour. Humans needed.`);
      return;
    }
    await act(token, { action: "restart", deploymentId: again.id, reason: "" });
    record(t.serviceId);
    await slack(`🔧 Seraphine: ${t.name} had crashed. Restarting it.`);
    await Bun.sleep(VERIFY_AFTER_MS);
    const after = currentOf(await listDeployments(t, token));
    await slack(
      after && after.status === "SUCCESS"
        ? `✅ Seraphine: ${t.name} is running again after a restart.`
        : `🚨 Seraphine: ${t.name} is still crashed after a restart (${after?.status || "unknown"}). Humans needed — check its logs in Railway.`,
    );
  } catch (e: any) {
    console.error(e);
    const msg = String(e?.message || e);
    const hint = /Not Authorized/i.test(msg) ? ` RAILWAY_TOKEN_AGENTS is expired or wrong.` : "";
    await slack(`⚠️ Seraphine error checking ${t.name}: ${msg.slice(0, 300)}${hint}`);
  } finally {
    busy.delete(t.serviceId);
  }
}

// ---- Playwright / journey / error-spike alerts (no hostname in the alert) ----
const APP_WEB = "https://app.finverified.ai";
const JOURNEYS = [
  `${APP_WEB}/`, `${APP_WEB}/login`, `${APP_WEB}/register`, `${APP_WEB}/waitlist`,
  `${APP_WEB}/compliance/check`, `${APP_WEB}/free-tools`, `${APP_WEB}/lender/login`,
  "https://api.finverified.ai/health", "https://finverified.ai/",
];

type Probe = { u: string; status: number; loc: string };

async function probe(u: string): Promise<Probe> {
  try {
    const r = await fetch(u, { redirect: "manual", signal: AbortSignal.timeout(20_000) });
    return { u, status: r.status, loc: r.headers.get("location") || "" };
  } catch {
    return { u, status: 0, loc: "" };
  }
}
const broken = (p: Probe) => p.status === 0 || p.status >= 500;
const short = (u: string) => u.replace("https://", "");

function alertName(body: any, raw: string): string {
  const a = body?.data?.attributes || body?.attributes || {};
  return String(a.name || a.cause || body?.name || raw.slice(0, 120));
}

function targetForUrl(u: string): Target | undefined {
  const h = new URL(u).hostname;
  return TARGETS.find((x) => x.match.includes(h));
}

async function newestDeployNote(): Promise<string> {
  const t = TARGETS.find((x) => x.serviceId === "46889cf7-00b4-4040-9575-6f940aaf33ec")!;
  const token = Bun.env[t.tokenVar];
  if (!token) return "";
  try {
    const cur = currentOf(await listDeployments(t, token));
    if (!cur) return "";
    const min = Math.round((Date.now() - new Date(cur.createdAt).getTime()) / 60000);
    return ` Newest app release went out ${min} min ago${min < 120 ? " — likely related" : ""}.`;
  } catch {
    return "";
  }
}

async function scenarioReport(name: string): Promise<{ bad: Probe[]; text: string }> {
  const first = await Promise.all(JOURNEYS.map(probe));
  let bad = first.filter(broken);
  if (bad.length) {
    await Bun.sleep(15_000);
    const second = await Promise.all(bad.map((p) => probe(p.u)));
    bad = second.filter(broken);
  }
  const redirects = first.filter((p) => p.status >= 300 && p.status < 400 && p.loc)
    .map((p) => `${short(p.u)} → ${p.loc}`);
  const text = bad.length
    ? `Broken: ${bad.map((p) => `${short(p.u)} (${p.status || "unreachable"})`).join(", ")}.`
    : `Every key page loads (${first.length} checked).${redirects.length ? ` Redirects: ${redirects.join("; ")}.` : ""}`;
  return { bad, text };
}

async function scenarioTriage(name: string) {
  busy.add("scenario");
  try {
    const r = await scenarioReport(name);
    if (!r.bad.length) {
      const note = await newestDeployNote();
      await slack(`🔎 Seraphine: alert "${name}". ${r.text} No outage, so I did NOT restart or roll back.${note} Humans: if this is a test alert, update the test; if it's an error spike, check the errors in Better Stack — a code fix goes through a PR.`);
      return;
    }
    await slack(`🚨 Seraphine: alert "${name}". ${r.text} Fixing now.`);
    const done = new Set<string>();
    for (const p of r.bad) {
      const t = targetForUrl(p.u);
      if (!t) { await slack(`🚨 Seraphine: ${short(p.u)} is broken and I don't manage it. Humans needed.`); continue; }
      if (done.has(t.serviceId) || busy.has(t.serviceId)) continue;
      done.add(t.serviceId);
      const token = Bun.env[t.tokenVar];
      if (!token) { await slack(`🚨 Seraphine: ${t.name} is broken but ${t.tokenVar} is not set. Humans needed.`); continue; }
      runFix(t, token, p.u);
    }
  } catch (e: any) {
    console.error(e);
    await slack(`⚠️ Seraphine scenario triage error: ${String(e?.message || e).slice(0, 300)}`);
  } finally {
    busy.delete("scenario");
  }
}

// ---- DNS alerts (never restart; repair the record or acknowledge what she saw working) ----
const CHECK_ONLY: Record<string, string> = {
  "walkthrough.finverified.ai": "https://walkthrough.finverified.ai",
  "academy.finverified.ai": "https://academy.finverified.ai/health",
};
const dnsEvents: number[] = [];

function isDnsAlert(body: any, raw: string): boolean {
  const a = body?.data?.attributes || body?.attributes || {};
  return /dns/i.test(String(a.cause || "")) || /dns lookup failure/i.test(raw);
}

function incidentIdOf(body: any): string {
  const id = body?.data?.id ?? body?.id ?? "";
  return /^\d+$/.test(String(id)) ? String(id) : "";
}

function checkUrlFor(host: string): string {
  return CHECK_ONLY[host] || TARGETS.find((x) => x.match.includes(host))?.healthUrl || `https://${host}`;
}

async function publicDns(host: string): Promise<string> {
  const resolvers: [string, string][] = [
    ["Google", `https://dns.google/resolve?name=${host}&type=A`],
    ["Cloudflare", `https://cloudflare-dns.com/dns-query?name=${host}&type=A`],
  ];
  const out: string[] = [];
  for (const [name, url] of resolvers) {
    try {
      const r = await fetch(url, { headers: { accept: "application/dns-json" }, signal: AbortSignal.timeout(8_000) });
      const j: any = await r.json();
      const ips = (j.Answer || []).filter((x: any) => x.type === 1).map((x: any) => x.data);
      out.push(`${name} ${ips.length ? "OK" : `EMPTY (status ${j.Status})`}`);
    } catch {
      out.push(`${name} lookup failed`);
    }
  }
  return out.join(", ");
}

async function ackIncident(id: string): Promise<string> {
  const tok = Bun.env.BETTERSTACK_API_TOKEN;
  if (!tok) return " (Not acknowledged yet: BETTERSTACK_API_TOKEN is not set.)";
  if (!id) return " (No incident id in the alert, so nothing to acknowledge.)";
  for (const v of ["v3", "v2"]) {
    try {
      const r = await fetch(`https://uptime.betterstack.com/api/${v}/incidents/${id}/acknowledge`, {
        method: "POST",
        headers: { Authorization: `Bearer ${tok}`, "Content-Type": "application/json" },
        body: JSON.stringify({ acknowledged_by: "Seraphine (auto: DNS blip, site confirmed up)" }),
        signal: AbortSignal.timeout(10_000),
      });
      if (r.ok) return " I acknowledged the incident so it stops calling.";
    } catch { /* try next version */ }
  }
  return " (Tried to acknowledge the incident but Better Stack refused — check BETTERSTACK_API_TOKEN.)";
}

async function dnsTriage(hosts: string[], id: string) {
  for (const h of hosts) {
    const key = "dns:" + h;
    if (busy.has(key)) continue;
    busy.add(key);
    try {
      const c = await confirmDownWith(() => urlUp(checkUrlFor(h)));
      const dns = await publicDns(h);
      const now = Date.now();
      dnsEvents.push(now);
      while (dnsEvents.length && now - dnsEvents[0] > 86_400_000) dnsEvents.shift();
      const n = dnsEvents.length;
      const cause = n >= 3 ? ` (${n} DNS alerts in the last 24h.)` : "";
      if (!c.down) {
        const ack = await ackIncident(id);
        await slack(`🌐 Seraphine: DNS blip on ${h}. Site is UP (${c.detail}); public DNS: ${dns}. No restart (restarts can't fix DNS).${ack}${cause}`);
      } else {
        const fix = await repairDns(h);
        await slack(`🚨 Seraphine: DNS alert on ${h} and the site is NOT loading (${c.detail}); public DNS: ${dns}. No restart (restarts can't fix DNS). ${fix.msg}${fix.changed ? "" : " Better Stack keeps calling."}${cause}`);
      }
    } catch (e: any) {
      console.error(e);
      await slack(`⚠️ Seraphine DNS triage error on ${h}: ${String(e?.message || e).slice(0, 300)}`);
    } finally {
      busy.delete(key);
    }
  }
}

async function dryRun(text: string) {
  if (text.startsWith("dns:")) {
    const h = text.slice(4);
    const c = await confirmDownWith(() => urlUp(checkUrlFor(h)));
    return {
      ok: true,
      msg: `[TEST — nothing changed] DNS check ${h}: site ${c.down ? "DOWN" : "UP"} (${c.detail}); public DNS: ${await publicDns(h)}. Better Stack token ${Bun.env.BETTERSTACK_API_TOKEN ? "set" : "NOT set"}. Cloudflare token ${Bun.env.CLOUDFLARE_API_TOKEN ? "set" : "NOT set"}; saved working copy of this record: ${goodDns.has(h) ? "yes" : "not yet"}. On a real alert I would ${c.down ? "put the record back in Cloudflare if it was changed or deleted, otherwise leave it ringing and say humans needed" : "acknowledge it and post a note"}. Never restarts for DNS.`,
    };
  }
  if (text === "cloudflare") {
    if (!Bun.env.CLOUDFLARE_API_TOKEN) return { ok: false, msg: "[TEST] CLOUDFLARE_API_TOKEN is not set yet, so I can't repair DNS." };
    try {
      const lines: string[] = [];
      for (const t of TARGETS) {
        const h = new URL(t.healthUrl).hostname;
        if (!inZone(h)) continue;
        const now = await cfRecords(h);
        lines.push(`${h}: Cloudflare has ${describe(now)}; saved working copy: ${goodDns.has(h) ? "yes" : "not yet"}`);
      }
      return { ok: true, msg: `[TEST — nothing changed] Cloudflare key works. ${lines.join("; ")}` };
    } catch (e: any) {
      return { ok: false, msg: `[TEST] Cloudflare key problem: ${String(e?.message || e).slice(0, 200)}` };
    }
  }
  if (text === "scenario") {
    const r = await scenarioReport("dry run");
    return { ok: true, msg: `[TEST — nothing changed] ${r.text}${r.bad.length ? " Would restart/roll back the broken service." : " Would NOT touch production."}${await newestDeployNote()}` };
  }
  if (text === "agents") {
    const token = Bun.env.RAILWAY_TOKEN_AGENTS;
    if (!token) return { ok: false, msg: "[TEST] RAILWAY_TOKEN_AGENTS is not set yet, so I can't see the agent services." };
    const lines: string[] = [];
    for (const s of STATUS_TARGETS) {
      try {
        const cur = currentOf(await listDeployments(asTarget(s), token));
        lines.push(`${s.name}: ${cur?.status || "no deployment"}`);
      } catch (e: any) {
        lines.push(`${s.name}: token rejected (${String(e?.message || e).slice(0, 80)})`);
      }
    }
    return { ok: true, msg: `[TEST — nothing changed] ${lines.join("; ")}` };
  }
  const r = resolveTarget(text);
  if (r.unknown.length) return { ok: false, msg: `Unmanaged host(s): ${r.unknown.join(", ")}. Would report "humans needed".` };
  const t = r.target;
  if (!t) return { ok: false, msg: "No matching service for that target." };
  const token = Bun.env[t.tokenVar];
  if (!token) return { ok: false, msg: `${t.name}: ${t.tokenVar} is not set yet. Would check the site and report "humans needed" if down.` };
  try {
    const deps = await listDeployments(t, token);
    const p1 = planRestart(deps);
    const p2 = planRollback(t, deps);
    const now = await isUp(t);
    return {
      ok: true,
      msg: `[TEST — nothing changed] ${t.name}. Token works. Site is ${now.up ? "UP" : "DOWN"} (${now.detail}). If it were down, step 1 would: ${p1.action} — ${p1.reason} If still down after 2 min, step 2 would: ${p2.action} — ${p2.reason}`,
    };
  } catch (e: any) {
    return { ok: false, msg: `[TEST] ${t.name}: ${t.tokenVar} does NOT work (${String(e?.message || e).slice(0, 120)}). Make a new Railway project token.` };
  }
}

// Key check: confirm every repair key works and say so in #alerts.
async function selfCheck(label = "started") {
  const seen = new Set<string>();
  const ok: string[] = [];
  const bad: string[] = [];
  const all = [...TARGETS, ...STATUS_TARGETS.map(asTarget)];
  for (const t of all) {
    if (seen.has(t.tokenVar)) continue;
    seen.add(t.tokenVar);
    const tok = Bun.env[t.tokenVar];
    if (!tok) { bad.push(`${t.tokenVar} (not set)`); continue; }
    try { await listDeployments(t, tok); ok.push(t.tokenVar); }
    catch { bad.push(`${t.tokenVar} (rejected)`); }
  }
  let cfTxt = " Cloudflare key NOT set (I can spot DNS problems but can't repair them).";
  if (Bun.env.CLOUDFLARE_API_TOKEN) {
    try { await zoneId(); cfTxt = " Cloudflare key works (I can repair DNS)."; }
    catch (e: any) { cfTxt = ` Cloudflare key NOT working (${String(e?.message || e).slice(0, 120)}).`; }
  }
  const bs = Bun.env.BETTERSTACK_API_TOKEN ? " Better Stack key is set." : " Better Stack key NOT set (DNS false alarms will still phone you).";
  const hb = Bun.env.BETTERSTACK_HEARTBEAT_URL ? " Heartbeat is on." : " Heartbeat NOT set (nobody will know if I get stuck).";
  await slack(bad.length
    ? `⚠️ Seraphine ${label}. Repair keys working: ${ok.join(", ") || "none"}. NOT working: ${bad.join(", ")} — I can't repair those until fixed.${cfTxt}${bs}${hb}`
    : `✅ Seraphine ${label}. All ${ok.length} repair keys work. I can repair app, API, sandbox, walkthrough, academy, the website and the agent platform.${cfTxt}${bs}${hb}`);
}

// ---- Patrol: Seraphine checks everything herself every 5 minutes ----
const PATROL_MS = 5 * 60_000;
const patrolDown = new Map<string, number>();
const domainNote = new Map<string, number>();
let lastReportDay = "";
let patrolling = false;

async function certDaysLeft(host: string): Promise<number | null> {
  try {
    const tls: any = await import("node:tls");
    return await new Promise((resolve) => {
      const s = tls.connect({ host, port: 443, servername: host, timeout: 10_000 }, () => {
        const c: any = s.getPeerCertificate();
        s.end();
        resolve(c?.valid_to ? Math.floor((new Date(c.valid_to).getTime() - Date.now()) / 86_400_000) : null);
      });
      s.on("error", () => resolve(null));
      s.on("timeout", () => { s.destroy(); resolve(null); });
    });
  } catch { return null; }
}

// Domain registration expiry (public registry lookup). Best effort.
async function domainDaysLeft(domain: string): Promise<number | null> {
  try {
    const r = await fetch(`https://rdap.org/domain/${domain}`, { redirect: "follow", signal: AbortSignal.timeout(15_000) });
    if (!r.ok) return null;
    const j: any = await r.json();
    const ev = (j.events || []).find((e: any) => /expiration/i.test(String(e.eventAction)));
    if (!ev?.eventDate) return null;
    return Math.floor((new Date(ev.eventDate).getTime() - Date.now()) / 86_400_000);
  } catch { return null; }
}

// Same page, but through Railway's own address (skips our DNS). If this works
// while the real address fails, it's a DNS/domain problem — a restart won't help.
function railwayUrl(t: Target): string | null {
  const h = t.match.find((x) => x.endsWith(".up.railway.app"));
  if (!h) return null;
  const u = new URL(t.healthUrl);
  if (u.hostname === h) return null; // already the Railway address
  return `https://${h}${u.pathname === "/" ? "" : u.pathname}`;
}

async function patrolWeb() {
  for (const t of TARGETS) {
    try {
      if (busy.has(t.serviceId)) continue;
      const host = new URL(t.healthUrl).hostname;
      const r = await isUp(t);
      if (r.up) {
        await snapshotDns(host); // save the working DNS record (every 30 min)
        if (patrolDown.has(t.serviceId)) {
          patrolDown.delete(t.serviceId);
          await slack(`✅ Seraphine patrol: ${t.name} is answering again (${r.detail}).`);
        }
        continue;
      }
      const ru = railwayUrl(t);
      if (ru && (await urlUp(ru)).up) {
        // App is fine; the problem is the address. Repair DNS if it's broken.
        const dnsIssue = await dnsBroken(t);
        const fix = dnsIssue
          ? await repairDns(host)
          : {
              changed: false,
              msg: r.detail === CERT_ERROR
                ? `It's the security certificate on our address. ${CERT_HINT}`
                : "Public DNS looks fine, so check the domain setup for this site in Railway and Cloudflare. Humans needed if it lasts.",
            };
        const last = domainNote.get(t.serviceId) || 0;
        if (fix.changed || Date.now() - last > 3_600_000) {
          domainNote.set(t.serviceId, Date.now());
          await slack(`🌐 Seraphine patrol: ${t.name} fails at its real address (${r.detail}) but the app itself is fine on Railway — no restart. ${fix.msg}`);
        }
        continue;
      }
      const token = Bun.env[t.tokenVar];
      if (!token) { await reportNoToken(t); continue; }
      if (!canAct(t.serviceId)) continue; // already used this hour's fixes; Better Stack keeps calling humans
      if (!patrolDown.has(t.serviceId)) {
        patrolDown.set(t.serviceId, Date.now());
        await slack(`👀 Seraphine patrol: ${t.name} failed my check (${r.detail}). Confirming and fixing.`);
      }
      runFix(t, token);
    } catch (e: any) {
      console.error("patrol error", t.name, e);
    }
  }
}

async function patrol() {
  if (patrolling) return;
  patrolling = true;
  try {
    await patrolWeb();
    for (const s of STATUS_TARGETS) {
      try { await checkStatusTarget(s); } catch (e) { console.error("agent check error", s.name, e); }
    }
    // Heartbeat: "I'm alive and I finished a patrol." If this stops, Better Stack calls Rick.
    const hb = Bun.env.BETTERSTACK_HEARTBEAT_URL;
    if (hb) {
      try { await fetch(hb, { signal: AbortSignal.timeout(10_000) }); }
      catch { console.error("heartbeat ping failed"); }
    }
  } finally {
    patrolling = false;
  }
}

async function dailyReport() {
  const lines: string[] = [];
  for (const t of TARGETS) {
    const r = await isUp(t);
    const host = new URL(t.healthUrl).hostname;
    const d = host.endsWith(".up.railway.app") ? null : await certDaysLeft(host);
    const certTxt = d === null ? "" : `, security cert ${d} days left${d < 30 ? " ⚠️ RENEW SOON" : ""}`;
    lines.push(`${r.up ? "✅" : "🚨"} ${t.name}: ${r.detail}${certTxt}`);
  }
  const agentTok = Bun.env.RAILWAY_TOKEN_AGENTS;
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
  lines.push(Bun.env.CLOUDFLARE_API_TOKEN
    ? `✅ DNS repair: working copies saved for ${saved.filter((h) => goodDns.has(h)).length} of ${saved.length} sites`
    : "⚠️ DNS repair: off (CLOUDFLARE_API_TOKEN not set)");
  await slack(`🗓️ Seraphine daily IT report\n${lines.join("\n")}`);
  await selfCheck("daily check");
}

async function handleWebhook(req: Request) {
  const raw = await req.text();
  let body: any = {};
  try { body = JSON.parse(raw); } catch { /* match on raw text */ }
  if (isResolvedEvent(body)) return Response.json({ ok: true, msg: "Resolved/ack event ignored." });

  // DNS alerts first: never restart or roll back for DNS.
  if (isDnsAlert(body, raw)) {
    const hosts = hostsIn(raw);
    if (hosts.length) {
      dnsTriage(hosts, incidentIdOf(body)); // background
      return Response.json({ ok: true, msg: `DNS alert for ${hosts.join(", ")}: checking. Never restarting for DNS.` });
    }
  }

  const r = resolveTarget(raw);
  if (r.unknown.length) {
    reportUnknown(r.unknown);
    return Response.json({ ok: false, msg: `Unmanaged host(s): ${r.unknown.join(", ")}. Checking and escalating.` });
  }
  const t = r.target;
  if (!t) {
    if (busy.has("scenario")) return Response.json({ ok: true, msg: "Already checking the journeys." });
    scenarioTriage(alertName(body, raw)); // background
    return Response.json({ ok: true, msg: "No hostname in alert. Checking every key page." });
  }
  if (busy.has(t.serviceId)) return Response.json({ ok: true, msg: "Already handling this one." });
  const token = Bun.env[t.tokenVar];
  if (!token) {
    reportNoToken(t);
    return Response.json({ ok: false, msg: `${t.tokenVar} not set. Checking and escalating.` });
  }

  runFix(t, token); // background: reply to Better Stack right away
  return Response.json({ ok: true, msg: `Checking ${t.name}` });
}

Bun.serve({
  port: Number(Bun.env.PORT || 3000),
  async fetch(req) {
    const url = new URL(req.url);
    if (url.pathname === "/" || url.pathname === "/health") {
      return Response.json({ ok: true, service: "seraphine-fixer" });
    }

    try {
      // Better Stack webhook: POST /betterstack (no secret needed; Seraphine verifies herself)
      if (url.pathname === "/betterstack" && req.method === "POST") {
        return await handleWebhook(req);
      }

      // Dry run (password-protected): GET /test?key=...&target=sandbox.finverified.ai
      //   target=dns:walkthrough.finverified.ai  -> DNS check, nothing changed
      //   target=cloudflare                     -> Cloudflare key + saved DNS copies, nothing changed
      //   target=scenario                       -> journey check, nothing changed
      //   target=agents                         -> agent platform status, nothing changed
      //   target=report                         -> post the daily IT report now
      if (url.pathname === "/test" && req.method === "GET") {
        const key = Bun.env.FIXER_KEY;
        if (!key || url.searchParams.get("key") !== key) return new Response("forbidden", { status: 403 });
        if (url.searchParams.get("target") === "report") { await dailyReport(); return Response.json({ ok: true, msg: "Daily report posted to #alerts." }); }
        return Response.json(await dryRun(url.searchParams.get("target") || ""));
      }
    } catch (e: any) {
      console.error(e);
      await slack(`⚠️ Seraphine fixer error: ${String(e?.message || e).slice(0, 300)}`);
      return Response.json({ ok: false, msg: "error" }, { status: 500 });
    }

    return new Response("not found", { status: 404 });
  },
});

console.log("seraphine-fixer listening");
setInterval(patrol, PATROL_MS);
setInterval(() => {
  const now = new Date();
  const day = now.toISOString().slice(0, 10);
  if (now.getUTCHours() === 12 && lastReportDay !== day) { lastReportDay = day; dailyReport(); }
}, 10 * 60_000);
selfCheck("restarted");
patrol();
