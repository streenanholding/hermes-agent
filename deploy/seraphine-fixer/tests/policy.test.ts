// The never-list is enforced in code: blocked writes throw before any request is sent.
import { beforeEach, describe, expect, test } from "bun:test";
import { AGENT_ENV, TARGETS } from "../src/config";
import { repairDns, goodDns } from "../src/dns";
import { NEVER_LIST, NeverListError, SAFE_LIST, checkCloudflare, checkRailway, mutationFields } from "../src/policy";
import { gql } from "../src/railway";
import { callsTo, json, net, on, reset } from "./helpers";

beforeEach(() => reset({}));

describe("never-list: Railway", () => {
  const blocked = [
    `mutation($i: VariableUpsertInput!) { variableUpsert(input: $i) }`,
    `mutation($i: VariableCollectionUpsertInput!) { variableCollectionUpsert(input: $i) }`,
    `mutation($id: String!) { serviceDelete(id: $id) }`,
    `mutation($id: String!) { volumeDelete(volumeId: $id) }`,
    `mutation($id: String!) { deploymentRemove(id: $id) }`,
    `mutation($i: ServiceInstanceUpdateInput!) { serviceInstanceUpdate(serviceId: "s", input: $i) }`,
    `mutation { projectMemberRemove(input: {}) }`,
    `mutation($id: String!) { deploymentRestart(id: $id) variableDelete(input: {}) }`,
  ];
  for (const q of blocked) {
    test(`blocks ${mutationFields(q).join("+")} without sending anything`, async () => {
      await expect(gql("tok", q, {})).rejects.toBeInstanceOf(NeverListError);
      expect(net.calls).toHaveLength(0);
    });
  }

  test("allows restart and rollback", () => {
    expect(() => checkRailway(`mutation($id: String!) { deploymentRestart(id: $id) }`)).not.toThrow();
    expect(() => checkRailway(`mutation($id: String!) { deploymentRollback(id: $id) }`)).not.toThrow();
  });

  test("reads are always allowed", () => {
    expect(() => checkRailway(`query { deployments(first: 1) { edges { node { id } } } }`)).not.toThrow();
  });

  test("stop is allowed only for a staging drill, never production", () => {
    const stop = `mutation($id: String!) { deploymentStop(id: $id) }`;
    expect(() => checkRailway(stop)).toThrow(NeverListError);
    expect(() => checkRailway(stop, { drillEnv: TARGETS[0].environmentId })).toThrow(NeverListError);
    expect(() => checkRailway(stop, { drillEnv: AGENT_ENV })).toThrow(NeverListError);
    expect(() => checkRailway(stop, { drillEnv: "staging-env-id" })).not.toThrow();
  });
});

describe("never-list: Cloudflare DNS", () => {
  test("never deletes a record", () => {
    expect(() => checkCloudflare("DELETE", "/zones/z/dns_records/r1")).toThrow(NeverListError);
  });
  test("never touches email records", () => {
    expect(() => checkCloudflare("POST", "/zones/z/dns_records", JSON.stringify({ type: "MX", content: "x" }))).toThrow(NeverListError);
    expect(() => checkCloudflare("PATCH", "/zones/z/dns_records/r1", JSON.stringify({ type: "TXT", content: "x" }))).toThrow(NeverListError);
  });
  test("never touches zone settings", () => {
    expect(() => checkCloudflare("PATCH", "/zones/z/settings/ssl", JSON.stringify({ value: "off" }))).toThrow(NeverListError);
  });
  test("may put back a website address record", () => {
    expect(() => checkCloudflare("POST", "/zones/z/dns_records", JSON.stringify({ type: "CNAME", content: "x" }))).not.toThrow();
    expect(() => checkCloudflare("PATCH", "/zones/z/dns_records/r1", JSON.stringify({ type: "A", content: "1.2.3.4" }))).not.toThrow();
  });

  test("repairDns puts back a changed record and sends no DELETE", async () => {
    reset({ CLOUDFLARE_API_TOKEN: "cf", CLOUDFLARE_ZONE_ID: "z" });
    goodDns.set("app.finverified.ai", [{ type: "CNAME", name: "app.finverified.ai", content: "good.up.railway.app", proxied: true, ttl: 1 }]);
    on((c) => c.url.includes("api.cloudflare.com") && c.method === "GET"
      ? json({ success: true, result: [{ id: "r1", type: "CNAME", name: "app.finverified.ai", content: "evil.example.com", proxied: true, ttl: 1 }] })
      : undefined);
    on((c) => (c.url.includes("api.cloudflare.com") ? json({ success: true, result: {} }) : undefined));
    const r = await repairDns("app.finverified.ai");
    expect(r.changed).toBe(true);
    const writes = callsTo("api.cloudflare.com").filter((c) => c.method !== "GET");
    expect(writes.map((w) => w.method)).toEqual(["PATCH"]);
    expect(writes[0].body.content).toBe("good.up.railway.app");
  });
});

test("the lists say what they mean", () => {
  const never = NEVER_LIST.join(" ");
  for (const w of ["code", "databases", "environment variables", "IAM", "users", "money"]) expect(never).toContain(w);
  expect(SAFE_LIST.join(" ")).toMatch(/2 healthy checks/);
});
