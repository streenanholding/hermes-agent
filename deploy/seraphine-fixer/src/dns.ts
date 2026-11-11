// DNS repair (Cloudflare). While a site works she saves a copy of its
// Cloudflare address record. If the site later breaks because that record was
// deleted or changed, she puts the saved copy back. She never deletes records
// and never touches MX/TXT (enforced by policy.checkCloudflare).

import { checkUrlFor, urlUp } from "./checks";
import type { Target } from "./config";
import { checkCloudflare, REPAIRABLE_TYPES } from "./policy";
import { rt, timeout } from "./runtime";

const CF_API = "https://api.cloudflare.com/client/v4";
const CF_ZONE = "finverified.ai";
const SNAPSHOT_EVERY_MS = 30 * 60_000;

export type CfRecord = { id?: string; type: string; name: string; content: string; proxied: boolean; ttl: number };
export const goodDns = new Map<string, CfRecord[]>(); // host -> records last seen while the site worked
const goodDnsAt = new Map<string, number>();
const dnsFixLog = new Map<string, number>(); // host -> last repair time
const repairing = new Set<string>();
let cfZoneId = "";

export const inZone = (h: string) => h === CF_ZONE || h.endsWith("." + CF_ZONE);

export function resetDns() {
  goodDns.clear(); goodDnsAt.clear(); dnsFixLog.clear(); repairing.clear(); cfZoneId = "";
}

async function cf(path: string, init: { method?: string; body?: string } = {}) {
  const tok = rt.env.CLOUDFLARE_API_TOKEN;
  if (!tok) throw new Error("CLOUDFLARE_API_TOKEN is not set");
  const method = init.method || "GET";
  checkCloudflare(method, path.split("?")[0], init.body);
  const r = await rt.fetch(CF_API + path, {
    method,
    body: init.body,
    headers: { Authorization: `Bearer ${tok}`, "Content-Type": "application/json" },
    signal: timeout(15_000),
  });
  const j: any = await r.json();
  if (!j.success) throw new Error(`Cloudflare said: ${JSON.stringify(j.errors || r.status).slice(0, 200)}`);
  return j;
}

export async function zoneId(): Promise<string> {
  if (cfZoneId) return cfZoneId;
  if (rt.env.CLOUDFLARE_ZONE_ID) return (cfZoneId = rt.env.CLOUDFLARE_ZONE_ID);
  const j = await cf(`/zones?name=${CF_ZONE}`);
  if (!j.result?.length) throw new Error("the Cloudflare key can't see the finverified.ai zone");
  return (cfZoneId = j.result[0].id);
}

export async function cfRecords(host: string): Promise<CfRecord[]> {
  const z = await zoneId();
  const j = await cf(`/zones/${z}/dns_records?name=${encodeURIComponent(host)}&per_page=100`);
  return (j.result || [])
    .filter((x: any) => REPAIRABLE_TYPES.includes(x.type))
    .map((x: any) => ({ id: x.id, type: x.type, name: x.name, content: x.content, proxied: Boolean(x.proxied), ttl: x.ttl }));
}

const sameRec = (a: CfRecord, b: CfRecord) =>
  a.type === b.type && a.content.toLowerCase() === b.content.toLowerCase() && a.proxied === b.proxied;

export function describe(recs: CfRecord[]): string {
  return recs.length ? recs.map((r) => `${r.type} → ${r.content}${r.proxied ? " (orange cloud)" : ""}`).join(", ") : "no address record";
}

// Called while a site is working: save its record as the known-good copy.
export async function snapshotDns(host: string) {
  if (!rt.env.CLOUDFLARE_API_TOKEN || !inZone(host)) return;
  if (rt.now() - (goodDnsAt.get(host) || 0) < SNAPSHOT_EVERY_MS) return;
  try {
    const recs = await cfRecords(host);
    if (recs.length) {
      goodDns.set(host, recs);
      goodDnsAt.set(host, rt.now());
    }
  } catch (e) {
    rt.error("dns snapshot error", host, e);
  }
}

export async function publicDns(host: string): Promise<string> {
  const resolvers: [string, string][] = [
    ["Google", `https://dns.google/resolve?name=${host}&type=A`],
    ["Cloudflare", `https://cloudflare-dns.com/dns-query?name=${host}&type=A`],
  ];
  const out: string[] = [];
  for (const [name, url] of resolvers) {
    try {
      const r = await rt.fetch(url, { headers: { accept: "application/dns-json" }, signal: timeout(8_000) });
      const j: any = await r.json();
      const ips = (j.Answer || []).filter((x: any) => x.type === 1).map((x: any) => x.data);
      out.push(`${name} ${ips.length ? "OK" : `EMPTY (status ${j.Status})`}`);
    } catch {
      out.push(`${name} lookup failed`);
    }
  }
  return out.join(", ");
}

// DNS guard used before ANY restart: if public DNS has no address for the
// site, it's a DNS problem and a restart can't help.
export async function dnsBroken(t: Target, checkUrl?: string): Promise<string | null> {
  const host = new URL(checkUrl || t.healthUrl).hostname;
  if (host.endsWith(".up.railway.app")) return null;
  const dns = await publicDns(host);
  return /EMPTY/.test(dns) ? `${host} — public DNS: ${dns}` : null;
}

export async function repairDns(host: string): Promise<{ changed: boolean; msg: string }> {
  if (!inZone(host)) return { changed: false, msg: `${host} isn't one of our Cloudflare sites.` };
  if (!rt.env.CLOUDFLARE_API_TOKEN) {
    return { changed: false, msg: "I can't repair DNS yet: CLOUDFLARE_API_TOKEN is not set in my variables. Humans needed." };
  }
  if (repairing.has(host)) return { changed: false, msg: "I'm already repairing it." };
  repairing.add(host);
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
    if (rt.now() - last < 3_600_000) {
      return { changed: false, msg: `I already repaired ${host} DNS within the last hour and it broke again. Not repeating — something or someone keeps changing it. Humans needed.` };
    }
    dnsFixLog.set(host, rt.now());
    const z = await zoneId();
    const done: string[] = [];
    for (const g of missing) {
      const sameType = now.find((n) => n.type === g.type);
      const clash = now.find((n) => n.type !== g.type && (g.type === "CNAME" || n.type === "CNAME"));
      if (sameType?.id) {
        await cf(`/zones/${z}/dns_records/${sameType.id}`, {
          method: "PATCH",
          body: JSON.stringify({ type: g.type, content: g.content, proxied: g.proxied, ttl: g.ttl }),
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
    await rt.sleep(60_000);
    const after = await urlUp(checkUrlFor(host));
    const dnsNow = await publicDns(host);
    return {
      changed: true,
      msg: `🛠️ I repaired it in Cloudflare: ${done.join("; ")}. ${after.up ? `✅ ${host} is loading again (${after.detail}).` : `Not loading yet (${after.detail}; public DNS: ${dnsNow}) — DNS changes can take a few minutes. Better Stack will close the incident when it's back.`}`,
    };
  } catch (e: any) {
    rt.error(e);
    return { changed: false, msg: `My DNS repair failed: ${String(e?.message || e).slice(0, 200)}. Humans needed.` };
  } finally {
    repairing.delete(host);
  }
}
