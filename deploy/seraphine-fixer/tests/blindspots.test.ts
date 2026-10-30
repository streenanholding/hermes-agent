// Blind-spot watch and Slack thread behaviour without a bot token.
import { beforeEach, describe, expect, test } from "bun:test";
import { blindSpotWatch, checkJobs, checkSmoke, checkSources } from "../src/blindspots";
import { rt } from "../src/runtime";
import { problem } from "../src/slack";
import { SLACK_ENV, T0, callsTo, json, on, reset } from "./helpers";

const SQL = { BETTERSTACK_SQL_URL: "https://sql.example", BETTERSTACK_SQL_USER: "u", BETTERSTACK_SQL_PASSWORD: "p" };
const dt = (ms: number) => new Date(ms).toISOString().replace("T", " ").replace("Z", "");

function lastLog(msAgo: number | null) {
  on((c) => c.url.startsWith("https://sql.example")
    ? new Response(JSON.stringify(msAgo === null ? { last: "1970-01-01 00:00:00", n: 0 } : { last: dt(T0 - msAgo), n: 12 }))
    : undefined);
}

beforeEach(() => reset({ ...SLACK_ENV, ...SQL }));

describe("log sources", () => {
  test("fresh source is fine", async () => {
    lastLog(5 * 60_000);
    expect((await checkSources())[0].ok).toBe(true);
  });
  test("silent for longer than the limit is a blind spot", async () => {
    lastLog(45 * 60_000);
    const [f] = await checkSources();
    expect(f.ok).toBe(false);
    expect(f.text).toMatch(/no logs for 45 min/);
  });
  test("limit is configurable", async () => {
    reset({ ...SLACK_ENV, ...SQL, BLINDSPOT_LOG_SILENCE_MIN: "120" });
    lastLog(45 * 60_000);
    expect((await checkSources())[0].ok).toBe(true);
  });
  test("no credentials = can't check, not 'fine'", async () => {
    reset({});
    expect((await checkSources())[0].ok).toBeNull();
  });
});

test("scheduled jobs are reported as not wired until a heartbeat line exists", async () => {
  expect((await checkJobs())[0]).toMatchObject({ ok: null, text: expect.stringContaining("not wired") });
});

describe("e2e-prod-smoke", () => {
  test("red since the first failure, with a link", async () => {
    reset({ GITHUB_ACTIONS_TOKEN: "gh" });
    on((c) => c.url.includes("api.github.com") ? json({
      workflow_runs: [
        { conclusion: "failure", created_at: "2026-10-30T06:00:00Z", html_url: "https://github.com/run/3" },
        { conclusion: "failure", created_at: "2026-10-28T06:00:00Z", html_url: "https://github.com/run/2" },
        { conclusion: "failure", created_at: "2026-10-26T06:00:00Z", html_url: "https://github.com/run/1" },
        { conclusion: "success", created_at: "2026-10-25T06:00:00Z", html_url: "https://github.com/run/0" },
      ],
    }) : undefined);
    const f = await checkSmoke();
    expect(f.ok).toBe(false);
    expect(f.text).toMatch(/last 3 runs failed, since 2026-10-26/);
    expect(callsTo("api.github.com")[0].method).toBe("GET");
  });
  test("green is fine", async () => {
    reset({ GITHUB_ACTIONS_TOKEN: "gh" });
    on((c) => c.url.includes("api.github.com") ? json({ workflow_runs: [{ conclusion: "success" }] }) : undefined);
    expect((await checkSmoke()).ok).toBe(true);
  });
});

describe("watch", () => {
  test("a blind spot posts once, bumps the count, and pages only when switched on", async () => {
    lastLog(3 * 3_600_000);
    await blindSpotWatch();
    await rt.sleep(5 * 60_000);
    await blindSpotWatch();
    expect(callsTo("chat.postMessage").filter((c) => /blind spot/.test(c.body.text))).toHaveLength(1);
    expect(callsTo("chat.update").length).toBeGreaterThan(0);
    expect(callsTo("/v3/incidents")).toHaveLength(0);

    reset({ ...SLACK_ENV, ...SQL, BLINDSPOT_PAGE: "on", BETTERSTACK_API_TOKEN: "bs" });
    lastLog(3 * 3_600_000);
    await blindSpotWatch();
    await blindSpotWatch();
    expect(callsTo("/v3/incidents").filter((c) => c.method === "POST")).toHaveLength(1);
  });
});

test("with only a webhook, repeats within 6 h are counted silently", async () => {
  reset({ SLACK_WEBHOOK_URL: "https://hooks.slack.com/x" });
  await problem("k", "first");
  await problem("k", "second");
  await problem("k", "third");
  expect(callsTo("hooks.slack.com")).toHaveLength(1);
});
