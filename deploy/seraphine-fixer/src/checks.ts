// Seraphine's own health checks. She never trusts an alert by itself: she
// confirms "down" with 2 failed checks and "fixed" with 2 healthy checks in a row.

import { CHECK_GAP_MS, HEALTHY_CHECKS, TARGETS, CHECK_ONLY, WATCHED_SUFFIXES, FIXER_HOST, WEBSITE_NAME, type Target } from "./config";
import { rt, timeout } from "./runtime";

export type Check = { up: boolean; detail: string };
export const CERT_ERROR = "certificate error";

// Tells a broken security certificate apart from a site that doesn't answer.
export function failDetail(e: any): string {
  const s = `${e?.code || ""} ${e?.message || ""} ${e?.cause?.code || ""} ${e?.cause?.message || ""}`;
  return /CERT|certificate|TLS|SSL|self.signed|altname/i.test(s) ? CERT_ERROR : "unreachable";
}

export async function urlUp(u: string, loose = false): Promise<Check> {
  try {
    const res = await rt.fetch(u, { redirect: "follow", signal: timeout(20_000) });
    return { up: loose ? res.status < 500 : res.ok, detail: `HTTP ${res.status}` };
  } catch (e: any) {
    return { up: false, detail: failDetail(e) };
  }
}

export const isUp = (t: Target) => urlUp(t.healthUrl, Boolean(t.okBelow500));

// Down only if it fails twice, 15 seconds apart.
export async function confirmDown(check: () => Promise<Check>): Promise<{ down: boolean; detail: string }> {
  const a = await check();
  if (a.up) return { down: false, detail: a.detail };
  await rt.sleep(CHECK_GAP_MS);
  const b = await check();
  return { down: !b.up, detail: b.detail };
}

export type Healthy = { healthy: boolean; at?: number; detail: string; flapped: boolean; checks: number };

// Checks every 15 s until it is healthy twice in a row, or until `untilMs`.
// A healthy answer followed by a failure resets the count (flapping), so a
// flapping service never counts as fixed.
export async function waitHealthy(check: () => Promise<Check>, untilMs: number): Promise<Healthy> {
  let streak = 0;
  let flapped = false;
  let checks = 0;
  let detail = "";
  for (;;) {
    const r = await check();
    checks++;
    detail = r.detail;
    if (r.up) {
      streak++;
      if (streak >= HEALTHY_CHECKS) return { healthy: true, at: rt.now(), detail, flapped, checks };
    } else {
      if (streak > 0) flapped = true;
      streak = 0;
    }
    if (rt.now() + CHECK_GAP_MS > untilMs) return { healthy: false, detail, flapped, checks };
    await rt.sleep(CHECK_GAP_MS);
  }
}

// ---- Matching an alert to a service ----

// Hostnames in the alert that belong to us. Email addresses (rick@finverified.ai) are skipped.
export function hostsIn(text: string): string[] {
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

export type Resolution = { target?: Target; hosts: string[]; unknown: string[] };

// Exact hostnames only. Unknown hosts are reported "humans needed", never guessed.
export function resolveTarget(text: string, targets: Target[] = TARGETS): Resolution {
  const hosts = hostsIn(text).filter((h) => h !== FIXER_HOST);
  const unknown = hosts.filter((h) => !targets.some((x) => x.match.includes(h)));
  if (unknown.length) return { hosts, unknown };
  const matched = targets.filter((x) => x.match.some((m) => hosts.includes(m)));
  const specific = matched.filter((x) => x.name !== WEBSITE_NAME);
  return { target: specific[0] || matched[0], hosts, unknown };
}

export function targetForUrl(u: string, targets: Target[] = TARGETS): Target | undefined {
  const h = new URL(u).hostname;
  return targets.find((x) => x.match.includes(h));
}

export function checkUrlFor(host: string): string {
  return CHECK_ONLY[host] || TARGETS.find((x) => x.match.includes(host))?.healthUrl || `https://${host}`;
}

// TLS certificate days left (null if it can't be read).
export async function certDaysLeft(host: string): Promise<number | null> {
  try {
    const tls: any = await import("node:tls");
    return await new Promise((resolve) => {
      const s = tls.connect({ host, port: 443, servername: host, timeout: 10_000 }, () => {
        const c: any = s.getPeerCertificate();
        s.end();
        resolve(c?.valid_to ? Math.floor((new Date(c.valid_to).getTime() - rt.now()) / 86_400_000) : null);
      });
      s.on("error", () => resolve(null));
      s.on("timeout", () => { s.destroy(); resolve(null); });
    });
  } catch { return null; }
}
