// #alerts posting. One Slack thread per problem: the same problem within 6 h
// updates the original message ("still happening, 6th time, last 08:12")
// instead of posting again, and follow-ups (restarting, back up) go in its thread.
//
// With SLACK_BOT_TOKEN + SLACK_ALERTS_CHANNEL she can edit and thread.
// With only SLACK_WEBHOOK_URL (incoming webhooks can't edit), repeats within
// 6 h are counted silently and follow-ups are posted as plain messages.
// Never logs the Slack link or token.

import { THREAD_WINDOW_MS } from "./config";
import { saveState, state, type Thread } from "./state";
import { hhmm, ordinal, rt, timeout } from "./runtime";

const botReady = () => Boolean(rt.env.SLACK_BOT_TOKEN && rt.env.SLACK_ALERTS_CHANNEL);

async function slackApi(method: string, body: Record<string, unknown>): Promise<any> {
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      const r = await rt.fetch(`https://slack.com/api/${method}`, {
        method: "POST",
        headers: { "Content-Type": "application/json; charset=utf-8", Authorization: `Bearer ${rt.env.SLACK_BOT_TOKEN}` },
        body: JSON.stringify({ channel: rt.env.SLACK_ALERTS_CHANNEL, ...body }),
        signal: timeout(10_000),
      });
      const j: any = await r.json();
      if (j.ok) return j;
      rt.error(`Slack ${method} failed (attempt ${attempt}): ${j.error}`);
    } catch (e: any) {
      rt.error(`Slack ${method} failed (attempt ${attempt}): ${String(e?.code || e?.name || "network error")}`);
    }
    if (attempt === 1) await rt.sleep(2_000);
  }
  return null;
}

async function webhook(text: string) {
  const url = rt.env.SLACK_WEBHOOK_URL;
  if (!url) return;
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      const r = await rt.fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
        signal: timeout(10_000),
      });
      if (r.ok) return;
      rt.error(`Slack post failed (attempt ${attempt}): HTTP ${r.status}`);
    } catch (e: any) {
      rt.error(`Slack post failed (attempt ${attempt}): ${String(e?.code || e?.name || "network error")}`);
    }
    if (attempt === 1) await rt.sleep(2_000);
  }
}

// A plain message (reports, self-checks). Returns the message ts when the bot is used.
export async function post(text: string, threadTs?: string): Promise<string | undefined> {
  rt.log(text);
  if (botReady()) {
    const j = await slackApi("chat.postMessage", { text, ...(threadTs ? { thread_ts: threadTs } : {}) });
    if (j) return j.ts;
  }
  await webhook(text);
  return undefined;
}

const repeatLine = (t: Thread) => `_still happening, ${ordinal(t.count)} time, last ${hhmm(t.last)}_`;

// Start or bump the thread for one problem. `key` names the problem
// (e.g. "down:<serviceId>", "alert:<name>", "blind:source:<table>").
export async function problem(key: string, text: string): Promise<{ isNew: boolean; count: number }> {
  const now = rt.now();
  const t = state.threads[key];
  if (t && now - t.last < THREAD_WINDOW_MS) {
    t.count++;
    t.last = now;
    rt.log(`[${key}] ${repeatLine(t)}`);
    if (t.ts && botReady()) await slackApi("chat.update", { ts: t.ts, text: `${t.text}\n${repeatLine(t)}` });
    saveState();
    return { isNew: false, count: t.count };
  }
  const prior = t && now - t.last < 24 * 3_600_000 ? ` _(${t.count} earlier this day)_` : "";
  const ts = await post(text + prior);
  state.threads[key] = { ts, text: text + prior, first: now, last: now, count: 1 };
  saveState();
  return { isNew: true, count: 1 };
}

// A step in an existing problem's story (restarting, back up, diagnosis).
export async function followUp(key: string, text: string) {
  const t = state.threads[key];
  if (t?.ts && botReady()) {
    rt.log(`[${key}] ${text}`);
    await slackApi("chat.postMessage", { text, thread_ts: t.ts });
    return;
  }
  await post(text);
}

// The problem is over; the next one starts a fresh thread.
export function closeThread(key: string) {
  const t = state.threads[key];
  if (t) t.last = 0;
}

export const threadOpen = (key: string) => {
  const t = state.threads[key];
  return Boolean(t && rt.now() - t.last < THREAD_WINDOW_MS);
};
