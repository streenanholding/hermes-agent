// Test harness: a fake clock and a fake internet. Nothing here reaches a real
// service. Each test describes how sites answer and what the APIs return,
// then checks which calls Seraphine made.

import { resetBudgetCache } from "../src/ai";
import { resetCertCache } from "../src/blindspots";
import { resetDns } from "../src/dns";
import { resetFix } from "../src/fix";
import { resetLimits } from "../src/policy";
import { boot, rt } from "../src/runtime";
import { resetState } from "../src/state";

export const T0 = Date.parse("2026-10-30T16:00:00Z");

export type Call = { url: string; method: string; body: any; headers: Record<string, string> };
type Handler = (c: Call) => Response | undefined | Promise<Response | undefined>;

export const net = {
  calls: [] as Call[],
  handlers: [] as Handler[],
  health: new Map<string, number[]>(), // url -> status codes, consumed in order (last repeats); 0 = unreachable
};

export const json = (b: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json", ...headers } });

export function setHealth(url: string, statuses: number[]) {
  net.health.set(url, [...statuses]);
}

export function on(h: Handler) {
  net.handlers.push(h);
}

export const callsTo = (part: string) => net.calls.filter((c) => c.url.includes(part));
export const mutations = () => callsTo("backboard.railway.com").filter((c) => /mutation/.test(c.body?.query || ""));
export const slackTexts = () =>
  net.calls.filter((c) => c.url.includes("slack.com/api/chat.") || c.url.includes("hooks.slack")).map((c) => String(c.body?.text || ""));

export function reset(env: Record<string, string> = {}) {
  let clock = T0;
  rt.now = () => clock;
  rt.sleep = async (ms: number) => { clock += ms; };
  rt.log = () => {};
  rt.error = () => {};
  rt.env = { ...env };
  boot.at = T0 - 2 * 3_600_000; // past the boot guard unless a test says otherwise
  net.calls = [];
  net.handlers = [];
  net.health = new Map();
  resetState(); resetLimits(); resetFix(); resetDns(); resetBudgetCache(); resetCertCache();

  let ts = 1000;
  rt.fetch = async (input: string, init: RequestInit = {}) => {
    const url = String(input);
    let body: any = init.body;
    try { body = typeof body === "string" ? JSON.parse(body) : body; } catch { /* plain text */ }
    const headers = Object.fromEntries(Object.entries((init.headers || {}) as Record<string, string>).map(([k, v]) => [k.toLowerCase(), v]));
    const call: Call = { url, method: (init.method || "GET").toUpperCase(), body, headers };
    net.calls.push(call);
    for (const h of net.handlers) {
      const r = await h(call);
      if (r) return r;
    }
    const seq = [...net.health.entries()].find(([u]) => url === u);
    if (seq) {
      const list = seq[1];
      const s = list.length > 1 ? list.shift()! : list[0];
      if (s === 0) throw Object.assign(new Error("connect ECONNREFUSED"), { code: "ECONNREFUSED" });
      return new Response("", { status: s });
    }
    if (url.includes("slack.com/api/chat.postMessage")) return json({ ok: true, ts: String(ts++) });
    if (url.includes("slack.com/api/chat.update")) return json({ ok: true });
    if (url.includes("dns.google") || url.includes("cloudflare-dns.com")) return json({ Status: 0, Answer: [{ type: 1, data: "1.2.3.4" }] });
    if (url.includes("uptime.betterstack.com")) return json({ data: {} });
    return json({ ok: true });
  };
}

// Railway: deployments for any service; mutations succeed.
export function railway(deployments: { id: string; status: string; ageMin: number }[]) {
  on((c) => {
    if (!c.url.includes("backboard.railway.com")) return;
    const q = c.body?.query || "";
    if (/mutation/.test(q)) return json({ data: { ok: true } });
    if (/deployments/.test(q)) {
      return json({
        data: {
          deployments: {
            edges: deployments.map((d) => ({ node: { id: d.id, status: d.status, createdAt: new Date(rt.now() - d.ageMin * 60_000).toISOString() } })),
          },
        },
      });
    }
    return json({ data: {} });
  });
}

export const SLACK_ENV = { SLACK_BOT_TOKEN: "xoxb-test", SLACK_ALERTS_CHANNEL: "C123" };
