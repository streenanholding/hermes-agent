// Better Stack Telemetry, read-only, through the SQL API (a ClickHouse HTTP
// connection made in Telemetry -> Integrations -> SQL API). Needs
// BETTERSTACK_SQL_URL, BETTERSTACK_SQL_USER, BETTERSTACK_SQL_PASSWORD.
// Raw log lines stay inside the fixer; only scrubbed patterns go anywhere.

import { DEFAULT_PROD_SOURCES } from "./config";
import { rt, timeout } from "./runtime";

export const telemetryReady = () =>
  Boolean(rt.env.BETTERSTACK_SQL_URL && rt.env.BETTERSTACK_SQL_USER && rt.env.BETTERSTACK_SQL_PASSWORD);

// Source table prefixes like "t534306_finverified_app_oct27". Only safe characters.
export function prodSources(): string[] {
  return (rt.env.BETTERSTACK_PROD_SOURCES || DEFAULT_PROD_SOURCES)
    .split(",").map((s) => s.trim()).filter((s) => /^t\d+_[a-z0-9_]+$/.test(s));
}

export async function sql(query: string): Promise<any[]> {
  if (!telemetryReady()) throw new Error("telemetry query credentials are not set");
  const auth = Buffer.from(`${rt.env.BETTERSTACK_SQL_USER}:${rt.env.BETTERSTACK_SQL_PASSWORD}`).toString("base64");
  const url = `${rt.env.BETTERSTACK_SQL_URL!.replace(/\/+$/, "")}?output_format_pretty_row_numbers=0`;
  const r = await rt.fetch(url, {
    method: "POST",
    headers: { Authorization: `Basic ${auth}`, "Content-Type": "plain/text" },
    body: `${query} FORMAT JSONEachRow`,
    signal: timeout(30_000),
  });
  if (!r.ok) throw new Error(`Better Stack SQL said HTTP ${r.status}`);
  const text = await r.text();
  return text.split("\n").filter(Boolean).map((l) => JSON.parse(l));
}

// Recent lines live in hot storage, older ones in S3; a source can have
// everything in S3 (checked against finverified_app_oct27, Oct 30), so
// every query reads both.
const logsOf = (src: string) =>
  `(SELECT dt, raw FROM remote(${src}_logs) UNION ALL SELECT dt, raw FROM s3Cluster(primary, ${src}_s3) WHERE _row_type = 1)`;

const parseDt = (s: string) => Date.parse(String(s).replace(" ", "T") + (/[zZ+]/.test(String(s).slice(-6)) ? "" : "Z"));

export type ErrorLine = { source: string; msg: string; n: number; last: number };

// Error-level lines in the last `minutes`, grouped by message.
export async function recentErrors(minutes = 30): Promise<ErrorLine[]> {
  const out: ErrorLine[] = [];
  for (const src of prodSources()) {
    const rows = await sql(
      `SELECT coalesce(JSONExtract(raw, '_pattern', 'Nullable(String)'), JSONExtract(raw, 'message', 'Nullable(String)'), JSONExtract(raw, 'msg', 'Nullable(String)'), substring(raw, 1, 400)) AS msg,
              count() AS n, max(dt) AS last
       FROM ${logsOf(src)}
       WHERE dt > now() - INTERVAL ${Math.floor(minutes)} MINUTE
         AND lower(if(JSONExtractString(raw, 'level') != '', JSONExtractString(raw, 'level'), JSONExtractString(raw, 'severity'))) IN ('error', 'fatal', 'critical')
       GROUP BY msg ORDER BY n DESC LIMIT 50`,
    );
    for (const r of rows) out.push({ source: src, msg: String(r.msg ?? ""), n: Number(r.n), last: parseDt(r.last) });
  }
  return out;
}

// When a source last received any log line (looks back 2 days).
export async function lastLogAt(src: string): Promise<number | null> {
  const rows = await sql(`SELECT max(dt) AS last, count() AS n FROM ${logsOf(src)} WHERE dt > now() - INTERVAL 2 DAY`);
  return rows[0] && Number(rows[0].n) > 0 ? parseDt(rows[0].last) : null;
}

// When a line containing `needle` last appeared in a source (looks back `hours`).
export async function lastMatchAt(src: string, needle: string, hours: number): Promise<number | null> {
  const safe = needle.replace(/\\/g, "\\\\").replace(/'/g, "\\'");
  const rows = await sql(
    `SELECT max(dt) AS last, count() AS n FROM ${logsOf(src)} WHERE dt > now() - INTERVAL ${Math.floor(hours)} HOUR AND position(raw, '${safe}') > 0`,
  );
  return rows[0] && Number(rows[0].n) > 0 ? parseDt(rows[0].last) : null;
}
