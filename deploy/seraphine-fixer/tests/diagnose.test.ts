// Error-alert diagnosis and AI metering: rulebook and cache make 0 model
// calls; at the cap there are 0 model calls but code paths still run; the
// model only ever sees scrubbed pattern text and a count.
import { beforeEach, describe, expect, test } from "bun:test";
import { aiDiagnose, capWarning, strongRiskSummary } from "../src/ai";
import { diagnoseAlert } from "../src/diagnose";
import { matchRule } from "../src/rulebook";
import { rt } from "../src/runtime";
import { state } from "../src/state";
import { SLACK_ENV, callsTo, json, on, reset, slackTexts } from "./helpers";

const ENV = {
  ...SLACK_ENV,
  SERAPHINE_LITELLM_KEY: "sk-seraphine-virtual",
  BETTERSTACK_SQL_URL: "https://sql.example",
  BETTERSTACK_SQL_USER: "u",
  BETTERSTACK_SQL_PASSWORD: "p",
};

const modelCalls = () => callsTo("/v1/chat/completions");

function logs(rows: { msg: string; n: number }[]) {
  on((c) => c.url.startsWith("https://sql.example")
    ? new Response(rows.map((r) => JSON.stringify({ msg: r.msg, n: r.n, last: "2026-10-30 15:59:00.000000" })).join("\n"))
    : undefined);
}

function litellm(spend: number, cap = 25) {
  on((c) => (c.url.endsWith("/key/info") ? json({ info: { spend, max_budget: cap } }) : undefined));
  on((c) => c.url.endsWith("/v1/chat/completions")
    ? json({ choices: [{ message: { content: "What's wrong: x\nLikely cause: y\nFix: z\nWho: Ashish" } }] }, 200, { "x-litellm-response-cost": "0.0012" })
    : undefined);
}

beforeEach(() => reset(ENV));

describe("rulebook", () => {
  test("a rulebook match makes 0 model calls", async () => {
    litellm(1);
    logs([{ msg: "S3 upload failed: AccessDenied: not authorized to perform: s3:PutObject on arn:aws:s3:::fv-id-capture", n: 7 }]);
    const text = await diagnoseAlert("ID-capture upload failing");
    expect(modelCalls()).toHaveLength(0);
    expect(text).toMatch(/IAM/);
    expect(text).toMatch(/s3:PutObject/);
    expect(state.ai.avoidedRulebook).toBe(1);
  });

  test("v1 rows", () => {
    expect(matchRule("ParameterNotFound: /finverified/prod/BEDROCK_MODEL")?.rule.id).toBe("ssm-parameter-missing");
    expect(matchRule("x", "ParameterNotFound: Parameter /finverified/prod/BEDROCK_MODEL not found")?.detail).toContain("/finverified/prod/BEDROCK_MODEL");
    expect(matchRule("[flywheel-bedrock] SSM GetParameter failed")?.rule.id).toBe("ssm-parameter-missing");
    expect(matchRule("PrismaClientInitializationError: Can't reach database server at db:<id>")?.rule.id).toBe("db-connection");
    expect(matchRule("connect ECONNREFUSED <ip>:#", "connect ECONNREFUSED 10.0.0.2:5432")?.rule.id).toBe("db-connection");
    expect(matchRule("stripe: HTTP 401 Invalid API Key provided")?.rule.id).toBe("vendor-key-401");
    expect(matchRule("getaddrinfo ENOTFOUND api.example.com")?.rule.id).toBe("cert-dns");
    expect(matchRule("PLAN_NOT_STARTED")?.rule).toMatchObject({ id: "product-4xx", infra: false });
    expect(matchRule("LOG_CANARY ok")?.rule.noise).toBe(true);
    // a user login 401 is not a vendor key problem
    expect(matchRule("login failed: 401 unauthorized")?.rule.id).not.toBe("vendor-key-401");
  });
});

describe("cache", () => {
  test("a cached pattern makes 0 model calls", async () => {
    litellm(1);
    const first = await aiDiagnose("[id-capture-retention] patient purge failed", 6);
    expect(first).toMatchObject({ source: "ai" });
    expect(modelCalls()).toHaveLength(1);
    const second = await aiDiagnose("[id-capture-retention] patient purge failed", 9);
    expect(second).toMatchObject({ source: "cache" });
    expect(modelCalls()).toHaveLength(1);
    expect(state.ai.avoidedCache).toBe(1);
  });

  test("same pattern with different ids hits the cache", async () => {
    litellm(1);
    await aiDiagnose("purge failed for loan 3f2504e0-4f89-11d3-9a0c-0305e82c3301", 1);
    await aiDiagnose("purge failed for loan 9a7b1c2d-1111-2222-3333-444455556666", 1);
    expect(modelCalls()).toHaveLength(1);
  });
});

describe("cap", () => {
  test("at the cap: 0 model calls, but code paths still run", async () => {
    litellm(25, 25);
    logs([
      { msg: "[id-capture-retention] patient purge failed", n: 6 }, // unknown -> would need AI
      { msg: "PrismaClientInitializationError: Can't reach database server", n: 3 }, // rulebook
    ]);
    const text = await diagnoseAlert("ID-capture purge failing");
    expect(modelCalls()).toHaveLength(0);
    expect(text).toMatch(/AI is paused/);
    expect(text).toMatch(/can't reach Postgres/i); // rulebook still answers
    expect(slackTexts().some((t) => t.includes("🩺"))).toBe(true); // still posted
  });

  test("without her key AI is off and nothing calls a model", async () => {
    reset({ ...ENV, SERAPHINE_LITELLM_KEY: "" });
    litellm(0);
    const r = await aiDiagnose("something new", 1);
    expect(r).toMatchObject({ blocked: expect.stringContaining("code-only") });
    expect(modelCalls()).toHaveLength(0);
  });

  test("at 80% she says so once a day and keeps working", async () => {
    litellm(21, 25);
    expect(await capWarning()).toMatch(/84%/);
    expect(await capWarning()).toBeNull();
    const r = await aiDiagnose("brand new pattern", 1);
    expect(r).toMatchObject({ source: "ai" });
  });

  test("falls back to her own ledger when LiteLLM can't be asked", async () => {
    on((c) => (c.url.endsWith("/key/info") ? json({}, 500) : undefined));
    state.ai.ledger.push({ at: rt.now(), cost: 30, model: "seraphine-fast" });
    const r = await aiDiagnose("brand new pattern", 1);
    expect(r).toMatchObject({ blocked: expect.stringContaining("paused") });
    expect(modelCalls()).toHaveLength(0);
  });
});

describe("only scrubbed patterns reach the model", () => {
  test("prompt has the pattern and count, no ids/emails/phones", async () => {
    litellm(1);
    logs([{ msg: "reminder send failed for jane@clinic.org phone 555-867-5309 loan 3f2504e0-4f89-11d3-9a0c-0305e82c3301", n: 4 }]);
    await diagnoseAlert("Reminder errors");
    const body = JSON.stringify(modelCalls()[0].body);
    expect(body).not.toMatch(/jane|clinic\.org|867|3f2504e0/);
    expect(body).toMatch(/reminder send failed/);
    expect(body).toMatch(/Count in the last 30 minutes: 4/);
    expect(modelCalls()[0].body.model).toBe("seraphine-fast");
    expect(modelCalls()[0].headers.authorization).toBe("Bearer sk-seraphine-virtual");
  });
});

describe("seraphine-strong", () => {
  test("at most once a week", async () => {
    litellm(1);
    expect(await strongRiskSummary("API runs 1 replica")).toBeTruthy();
    expect(await strongRiskSummary("API runs 1 replica")).toBeNull();
    expect(modelCalls().map((c) => c.body.model)).toEqual(["seraphine-strong"]);
  });
});

describe("one thread per problem", () => {
  test("the same alert within 6 h updates the original message instead of posting", async () => {
    logs([{ msg: "[id-capture-retention] patient purge failed", n: 6 }]);
    litellm(1);
    await diagnoseAlert("ID-capture purge failing");
    for (let i = 0; i < 5; i++) {
      await rt.sleep(30 * 60_000);
      await diagnoseAlert("ID-capture purge failing");
    }
    expect(callsTo("chat.postMessage")).toHaveLength(1);
    const updates = callsTo("chat.update");
    expect(updates).toHaveLength(5);
    expect(updates[4].body.text).toMatch(/still happening, 6th time, last \d\d:\d\d/);
    expect(callsTo("sql.example")).toHaveLength(1); // no re-query, no re-diagnosis
  });

  test("after 6 h quiet it starts a new thread", async () => {
    logs([{ msg: "x failed", n: 1 }]);
    await diagnoseAlert("Some alert");
    await rt.sleep(7 * 3_600_000);
    await diagnoseAlert("Some alert");
    expect(callsTo("chat.postMessage")).toHaveLength(2);
  });

  test("a product cause opens one Linear Bug, then comments on it", async () => {
    reset({ ...ENV, LINEAR_API_KEY: "lin" });
    logs([{ msg: "PLAN_NOT_STARTED", n: 40 }]);
    let created = 0;
    on((c) => {
      if (!c.url.includes("api.linear.app")) return;
      const q = c.body.query as string;
      if (q.includes("issues(")) return json({ data: { issues: { nodes: created ? [{ id: "i1", identifier: "FIN-9", url: "u" }] : [] } } });
      if (q.includes("issueLabels")) return json({ data: { issueLabels: { nodes: [{ id: "bug" }] } } });
      if (q.includes("issueCreate")) { created++; return json({ data: { issueCreate: { issue: { identifier: "FIN-9", url: "u" } } } }); }
      if (q.includes("commentCreate")) return json({ data: { commentCreate: { success: true } } });
    });
    const t1 = await diagnoseAlert("Plan errors");
    expect(t1).toMatch(/opened FIN-9/);
    await rt.sleep(7 * 3_600_000);
    const t2 = await diagnoseAlert("Plan errors");
    expect(t2).toMatch(/updated FIN-9/);
    expect(created).toBe(1);
    expect(modelCalls()).toHaveLength(0);
  });
});
