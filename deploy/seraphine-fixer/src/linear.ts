// One Linear Bug per non-infra problem: opened the first time, commented on
// after that. Needs LINEAR_API_KEY. Text is always scrubbed before it gets here.

import { DEFAULT_LINEAR_TEAM } from "./config";
import { rt, timeout } from "./runtime";

async function linear(query: string, variables: Record<string, unknown>): Promise<any> {
  const r = await rt.fetch("https://api.linear.app/graphql", {
    method: "POST",
    headers: { Authorization: String(rt.env.LINEAR_API_KEY), "Content-Type": "application/json" },
    body: JSON.stringify({ query, variables }),
    signal: timeout(15_000),
  });
  const j: any = await r.json();
  if (j.errors) throw new Error(JSON.stringify(j.errors).slice(0, 200));
  return j.data;
}

// Returns "FIN-123 (url)" or a reason it couldn't.
export async function upsertBug(title: string, body: string): Promise<string> {
  if (!rt.env.LINEAR_API_KEY) return "no Linear Bug: LINEAR_API_KEY is not set";
  const teamId = rt.env.LINEAR_TEAM_ID || DEFAULT_LINEAR_TEAM;
  try {
    const found = await linear(
      `query($team: ID!, $title: String!) {
         issues(first: 1, filter: { team: { id: { eq: $team } }, title: { eq: $title }, state: { type: { nin: ["completed", "canceled"] } } }) {
           nodes { id identifier url }
         }
       }`,
      { team: teamId, title },
    );
    const open = found.issues.nodes[0];
    if (open) {
      await linear(`mutation($id: String!, $body: String!) { commentCreate(input: { issueId: $id, body: $body }) { success } }`, { id: open.id, body });
      return `updated ${open.identifier} (${open.url})`;
    }
    const labels = await linear(
      `query($team: ID!) { issueLabels(first: 5, filter: { name: { eqIgnoreCase: "Bug" }, team: { id: { eq: $team } } }) { nodes { id } } }`,
      { team: teamId },
    ).catch(() => ({ issueLabels: { nodes: [] } }));
    const made = await linear(
      `mutation($input: IssueCreateInput!) { issueCreate(input: $input) { issue { identifier url } } }`,
      { input: { teamId, title, description: body, labelIds: labels.issueLabels.nodes.map((n: any) => n.id) } },
    );
    const i = made.issueCreate.issue;
    return `opened ${i.identifier} (${i.url})`;
  } catch (e: any) {
    return `Linear Bug failed (${String(e?.message || e).slice(0, 120)})`;
  }
}
