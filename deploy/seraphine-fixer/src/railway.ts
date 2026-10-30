// Railway: read deployments, restart, roll back. Every mutation is checked
// against the safe list before it is sent (policy.checkRailway).

import { ROLLBACK_WINDOW_MIN, type Target } from "./config";
import { checkRailway } from "./policy";
import { rt } from "./runtime";

const RAILWAY_API = "https://backboard.railway.com/graphql/v2";

export async function gql(token: string, query: string, variables: Record<string, unknown>, opts: { drillEnv?: string } = {}) {
  checkRailway(query, opts);
  const res = await rt.fetch(RAILWAY_API, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Project-Access-Token": token },
    body: JSON.stringify({ query, variables }),
  });
  const json: any = await res.json();
  if (json.errors) throw new Error(JSON.stringify(json.errors));
  return json.data;
}

export type Deployment = { id: string; status: string; createdAt: string };

export async function listDeployments(t: Target, token: string): Promise<Deployment[]> {
  const data = await gql(
    token,
    `query($input: DeploymentListInput!) {
       deployments(first: 10, input: $input) { edges { node { id status createdAt } } }
     }`,
    { input: { projectId: t.projectId, environmentId: t.environmentId, serviceId: t.serviceId } },
  );
  const nodes: Deployment[] = data.deployments.edges.map((e: any) => e.node);
  return nodes.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
}

// Replica count, for the weekly risk list ("API runs 1 replica").
export async function replicas(t: Target, token: string): Promise<number | null> {
  try {
    const d = await gql(token, `query($s: String!, $e: String!) { serviceInstance(serviceId: $s, environmentId: $e) { numReplicas } }`, {
      s: t.serviceId, e: t.environmentId,
    });
    return d?.serviceInstance?.numReplicas ?? 1;
  } catch { return null; }
}

export type Plan = { action: "restart" | "rollback" | "none"; deploymentId?: string; reason: string };

const IN_PROGRESS = ["BUILDING", "DEPLOYING", "INITIALIZING", "QUEUED", "WAITING"];

export function currentOf(deps: Deployment[]) {
  return deps.find((d) => d.status === "SUCCESS" || d.status === "CRASHED");
}

// Step 1: always restart first. A restart can never undo a fix.
export function planRestart(deps: Deployment[]): Plan {
  if (deps.length && IN_PROGRESS.includes(deps[0].status)) {
    return { action: "none", reason: `A deploy is already in progress (${deps[0].status}).` };
  }
  const current = currentOf(deps);
  if (!current) return { action: "none", reason: "No running or crashed deployment found." };
  return { action: "restart", deploymentId: current.id, reason: `Restarting (status was ${current.status}).` };
}

// Step 2: only if still down after the restart, and only if the newest deploy is recent.
export function planRollback(t: Target, deps: Deployment[]): Plan {
  if (!t.allowRollback) return { action: "none", reason: "Rollback is turned off for this service." };
  if (deps.length && IN_PROGRESS.includes(deps[0].status)) {
    return { action: "none", reason: `A deploy is in progress (${deps[0].status}).` };
  }
  const current = currentOf(deps);
  if (!current) return { action: "none", reason: "No current deployment found." };
  const ageMin = (rt.now() - new Date(current.createdAt).getTime()) / 60000;
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

export async function act(token: string, plan: Plan) {
  if (plan.action === "restart") {
    await gql(token, `mutation($id: String!) { deploymentRestart(id: $id) }`, { id: plan.deploymentId });
  } else if (plan.action === "rollback") {
    await gql(token, `mutation($id: String!) { deploymentRollback(id: $id) }`, { id: plan.deploymentId });
  }
}
