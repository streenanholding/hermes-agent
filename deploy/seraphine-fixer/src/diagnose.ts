// Diagnose an error alert (anything that isn't an outage). Pull the last 30
// min of error lines, group them by pattern, and explain each one:
//   rulebook (code, $0) -> cached AI diagnosis ($0) -> seraphine-fast (metered)
//   -> if AI is off or capped: "unknown pattern, humans", code paths still run.
// One message per problem; the same alert within 6 h only bumps the count.

import { aiDiagnose, noteRulebookHit } from "./ai";
import { upsertBug } from "./linear";
import { matchRule, ruleText } from "./rulebook";
import { errText, rt } from "./runtime";
import { patternOf } from "./scrub";
import { problem, threadOpen } from "./slack";
import { recentErrors, telemetryReady } from "./telemetry";

type Group = { pattern: string; raw: string; n: number };

function group(rows: { msg: string; n: number }[]): Group[] {
  const by = new Map<string, Group>();
  for (const r of rows) {
    const p = patternOf(r.msg);
    if (!p) continue;
    const g = by.get(p) || { pattern: p, raw: r.msg, n: 0 };
    g.n += r.n;
    by.set(p, g);
  }
  return [...by.values()];
}

// Patterns that share words with the alert name come first, then by count.
function rank(groups: Group[], alertName: string): Group[] {
  const words = new Set((alertName.toLowerCase().match(/[a-z]{4,}/g) || []).filter((w) => !["alert", "failing", "error", "errors"].includes(w)));
  const score = (g: Group) => (g.pattern.toLowerCase().match(/[a-z]{4,}/g) || []).filter((w) => words.has(w)).length;
  return groups.sort((a, b) => score(b) - score(a) || b.n - a.n);
}

export type Explained = { pattern: string; n: number; text: string; how: "rulebook" | "cache" | "ai" | "humans"; productBug: boolean; noise: boolean };

export async function explain(pattern: string, raw: string, n: number): Promise<Explained> {
  const m = matchRule(pattern, raw);
  if (m) {
    noteRulebookHit();
    return { pattern, n, text: ruleText(m), how: "rulebook", productBug: !m.rule.infra, noise: Boolean(m.rule.noise) };
  }
  const ai = await aiDiagnose(pattern, n);
  if ("blocked" in ai) {
    return { pattern, n, text: `Not in my rulebook. ${ai.blocked} Humans: look at this pattern in Better Stack.`, how: "humans", productBug: false, noise: false };
  }
  return { pattern, n, text: ai.text, how: ai.source, productBug: /Who:\s*Ashish/i.test(ai.text) && !/postgres|database/i.test(ai.text), noise: false };
}

const tag = { rulebook: "rulebook", cache: "AI, cached", ai: "AI", humans: "needs a human" };

export async function diagnoseAlert(alertName: string, pagesNote = ""): Promise<string> {
  const key = `alert:${patternOf(alertName).toLowerCase()}`;
  if (threadOpen(key)) {
    await problem(key, "");
    return "";
  }

  let groups: Group[] = [];
  let note = "";
  if (!telemetryReady()) note = "I can't read the logs yet (Better Stack SQL credentials not set), so this is from the alert name only.";
  else {
    try {
      groups = rank(group(await recentErrors(30)), alertName).slice(0, 3);
      if (!groups.length) note = "No error lines in the last 30 minutes.";
    } catch (e) {
      note = `I couldn't read the logs (${errText(e)}).`;
    }
  }
  if (!groups.length) groups = [{ pattern: patternOf(alertName), raw: alertName, n: 1 }];

  const parts: string[] = [];
  const bugs: string[] = [];
  for (const g of groups) {
    const x = await explain(g.pattern, g.raw, g.n);
    parts.push(`• "${x.pattern}" ×${x.n} _(${tag[x.how]})_\n${x.text.split("\n").map((l) => `   ${l}`).join("\n")}`);
    if (x.productBug) {
      bugs.push(await upsertBug(`[Seraphine] ${x.pattern.slice(0, 90)}`, `Alert: ${patternOf(alertName)}\nPattern: ${x.pattern}\nCount (30 min): ${x.n}\n\n${x.text}`));
    }
  }
  const text =
    `🩺 Seraphine: alert "${patternOf(alertName)}". ${pagesNote ? pagesNote + " " : ""}No outage, so I did NOT restart or roll back.${note ? " " + note : ""}\n` +
    parts.join("\n") +
    (bugs.length ? `\nLinear: ${bugs.join("; ")}` : "");
  await problem(key, text);
  rt.log(JSON.stringify({ event: "diagnosis", alert: patternOf(alertName), how: groups.length }));
  return text;
}
