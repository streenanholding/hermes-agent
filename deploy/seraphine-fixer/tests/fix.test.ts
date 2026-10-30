// Outage paths: down / up / flapping, rate limits, and "acknowledge only when healthy".
import { beforeEach, describe, expect, test } from "bun:test";
import { incidentOf } from "../src/betterstack";
import { TARGETS, WINDOW_MS } from "../src/config";
import { attachIncident, closeLoop, dnsTriage, runFix } from "../src/fix";
import { boot, rt } from "../src/runtime";
import { state } from "../src/state";
import { SLACK_ENV, T0, callsTo, mutations, net, railway, reset, setHealth, slackTexts } from "./helpers";

const net_index = (c: unknown) => net.calls.indexOf(c as any);

const WEB = TARGETS.find((t) => t.healthUrl === "https://app.finverified.ai")!; // rollback allowed
const API = TARGETS[0]; // restart only
const inc = (id = "555", startedAt = T0) => ({ id, startedAt, name: "app.finverified.ai is down", cause: "Status 502" });
const ENV = { RAILWAY_TOKEN_APP: "rw", BETTERSTACK_API_TOKEN: "bs", ...SLACK_ENV };

const acks = () => callsTo("uptime.betterstack.com").filter((c) => c.url.endsWith("/acknowledge"));
const resolves = () => callsTo("uptime.betterstack.com").filter((c) => c.url.endsWith("/resolve"));

beforeEach(() => {
  reset(ENV);
  railway([{ id: "dep-new", status: "SUCCESS", ageMin: 30 }, { id: "dep-old", status: "REMOVED", ageMin: 600 }]);
});

describe("down", () => {
  test("restart, healthy twice, then acknowledge and resolve inside 4 minutes", async () => {
    setHealth(WEB.healthUrl, [502, 502, 200, 200]);
    const rec = await runFix(WEB, "rw", { incident: inc() });

    expect(mutations().map((m) => m.body.query)).toEqual([expect.stringContaining("deploymentRestart")]);
    expect(acks()).toHaveLength(1);
    expect(resolves()).toHaveLength(1);
    // acknowledge comes before resolve
    expect(net_index(acks()[0])).toBeLessThan(net_index(resolves()[0]));
    expect(rec.outcome).toBe("fixed");
    expect(rec.silenced).toBe(true);
    expect(rec.closedAt! - T0).toBeLessThan(WINDOW_MS);
    // a note goes on the incident
    expect(callsTo("/comments")[0].body.content).toMatch(/restarted .* healthy since/);
    // time-to-fix is logged for every incident
    expect(state.fixes).toHaveLength(1);
    expect(state.fixes[0].fixedAt).toBeDefined();
    expect(slackTexts().some((t) => /nobody was called/.test(t))).toBe(true);
  });

  test("still down after restart: no acknowledge, call goes out", async () => {
    setHealth(API.healthUrl, [502]);
    const rec = await runFix(API, "rw", { incident: inc() });
    expect(mutations()).toHaveLength(1); // restart only; the API never rolls back
    expect(acks()).toHaveLength(0);
    expect(resolves()).toHaveLength(0);
    expect(rec.outcome).toBe("humans");
    expect(slackTexts().some((t) => /Better Stack is calling/.test(t))).toBe(true);
  });

  test("rollback fixes it after minute 4: resolved, but marked as not silenced", async () => {
    // fail, fail (confirm) ... stays down through the restart window, then healthy after rollback
    setHealth(WEB.healthUrl, [502, 502, 502, 502, 502, 502, 502, 502, 502, 502, 200, 200]);
    railway([{ id: "dep-new", status: "SUCCESS", ageMin: 30 }, { id: "dep-old", status: "REMOVED", ageMin: 600 }]);
    // the incident started 3 minutes before the webhook reached her
    const rec = await runFix(WEB, "rw", { incident: inc("555", T0 - 3 * 60_000) });
    expect(mutations().map((m) => /deploymentRollback/.test(m.body.query))).toEqual([false, true]);
    expect(rec.outcome).toBe("fixed");
    expect(resolves()).toHaveLength(1);
    expect(rec.silenced).toBe(false);
    expect(slackTexts().some((t) => /already gone out at minute 4/.test(t))).toBe(true);
  });
});

describe("up", () => {
  test("alert but the site answers: no restart, no acknowledge", async () => {
    setHealth(WEB.healthUrl, [200]);
    const rec = await runFix(WEB, "rw", { incident: inc() });
    expect(rec.outcome).toBe("up");
    expect(mutations()).toHaveLength(0);
    expect(acks()).toHaveLength(0);
  });

  test("one failed check then up is not 'down'", async () => {
    setHealth(WEB.healthUrl, [502, 200]);
    await runFix(WEB, "rw", { incident: inc() });
    expect(mutations()).toHaveLength(0);
  });
});

describe("flapping", () => {
  test("up/down/up/down after restart never counts as fixed and is never acknowledged", async () => {
    setHealth(API.healthUrl, [502, 502, 200, 502, 200, 502, 200, 502, 200, 502, 200, 502]);
    const rec = await runFix(API, "rw", { incident: inc() });
    expect(acks()).toHaveLength(0);
    expect(resolves()).toHaveLength(0);
    expect(rec.outcome).toBe("humans");
    expect(slackTexts().some((t) => /flapping/.test(t))).toBe(true);
  });
});

describe("acknowledge only when healthy", () => {
  test("closeLoop refuses without 2 healthy checks", async () => {
    attachIncident(WEB.serviceId, inc());
    const rec = { service: "x", serviceId: WEB.serviceId, incidentIds: [], startedAt: T0, detectedAt: T0, silenced: false, outcome: "humans" as const };
    await expect(closeLoop(WEB.serviceId, rec, "note", { healthy: false, detail: "HTTP 502", flapped: false, checks: 1 })).rejects.toThrow();
    expect(acks()).toHaveLength(0);
  });

  test("an incident that arrives while she is fixing joins the fix and is closed with it", async () => {
    setHealth(WEB.healthUrl, [502, 502, 200, 200]);
    const p = runFix(WEB, "rw"); // started by patrol, no incident yet
    attachIncident(WEB.serviceId, inc("777"));
    await p;
    expect(acks().map((c) => c.url)).toEqual([expect.stringContaining("/incidents/777/acknowledge")]);
  });

  test("without a Better Stack token nothing is silenced and she says so", async () => {
    reset({ RAILWAY_TOKEN_APP: "rw", ...SLACK_ENV });
    railway([{ id: "d", status: "SUCCESS", ageMin: 30 }]);
    setHealth(WEB.healthUrl, [502, 502, 200, 200]);
    await runFix(WEB, "rw", { incident: inc() });
    expect(acks()).toHaveLength(0);
    expect(slackTexts().some((t) => /BETTERSTACK_API_TOKEN is not set/.test(t))).toBe(true);
  });

  test("DNS blip is acknowledged only after 2 healthy checks", async () => {
    setHealth("https://walkthrough.finverified.ai", [200, 200, 200]);
    await dnsTriage(["walkthrough.finverified.ai"], inc("901"));
    expect(acks()).toHaveLength(1);

    reset(ENV);
    setHealth("https://walkthrough.finverified.ai", [200, 502, 200, 502]);
    await dnsTriage(["walkthrough.finverified.ai"], inc("902"));
    expect(acks()).toHaveLength(0);
  });

  test("the webhook's started_at drives the window", () => {
    const i = incidentOf({ data: { id: "42", attributes: { started_at: new Date(T0 - 60_000).toISOString(), name: "x" } } }, T0);
    expect(i).toMatchObject({ id: "42", startedAt: T0 - 60_000 });
    expect(incidentOf({ data: { id: "abc" } }, T0)).toMatchObject({ id: "", startedAt: T0 });
  });
});

describe("rate limits", () => {
  test("max 2 actions per service per hour, then humans", async () => {
    for (let i = 0; i < 3; i++) {
      setHealth(API.healthUrl, [502, 502, 200, 200]);
      await runFix(API, "rw", { incident: inc(String(100 + i)) });
      await rt.sleep(5 * 60_000);
    }
    expect(mutations()).toHaveLength(2);
    expect(slackTexts().some((t) => /used my fixes for this hour/.test(t))).toBe(true);
  });

  test("only 1 action in her first hour after she restarts (boot guard)", async () => {
    boot.at = T0;
    for (let i = 0; i < 2; i++) {
      setHealth(API.healthUrl, [502, 502, 200, 200]);
      await runFix(API, "rw", { incident: inc(String(200 + i)) });
    }
    expect(mutations()).toHaveLength(1);
  });

  test("limits reset after an hour", async () => {
    for (let i = 0; i < 2; i++) {
      setHealth(API.healthUrl, [502, 502, 200, 200]);
      await runFix(API, "rw", { incident: inc(String(300 + i)) });
    }
    await rt.sleep(61 * 60_000);
    setHealth(API.healthUrl, [502, 502, 200, 200]);
    await runFix(API, "rw", { incident: inc("399") });
    expect(mutations()).toHaveLength(3);
  });
});
