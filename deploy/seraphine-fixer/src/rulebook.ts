// The rulebook: known causes, matched by plain code ($0 AI). Each AI
// diagnosis Rick confirms becomes a new row here (by PR), so AI use shrinks
// over time. Rules match the scrubbed pattern; `detail` may read the raw line
// locally to name a parameter or permission (never sent anywhere else).

export type Rule = {
  id: string;
  test: RegExp;
  also?: RegExp; // must also match (keeps broad rules narrow)
  what: string;
  cause: string;
  fix: string;
  who: string;
  infra: boolean; // false = product issue -> Linear Bug
  noise?: boolean; // not a real error
  detail?: (raw: string) => string;
};

export const RULEBOOK: Rule[] = [
  {
    id: "log-canary",
    test: /LOG_CANARY/,
    what: "Log canary line.",
    cause: "The app writes this on purpose to prove logging works. It is logged at error level so it is never filtered out.",
    fix: "Nothing to fix.",
    who: "Nobody",
    infra: true,
    noise: true,
  },
  {
    id: "ticket-test-line",
    test: /^FIN-#? ?TEST\b|\bTEST (web|api):/,
    what: "Test log line from a ticket.",
    cause: "Someone tested logging or alerts with fake data.",
    fix: "Nothing to fix. If it keeps appearing, remove the test from the code.",
    who: "Nobody",
    infra: true,
    noise: true,
  },
  {
    id: "s3-access-denied",
    test: /AccessDenied|not authorized to perform:? ?s3:|S3.{0,40}(403|Forbidden)/i,
    what: "S3 says Access Denied.",
    cause: "The app's AWS IAM role is missing an S3 permission, or the bucket policy blocks it.",
    fix: "Add the missing S3 permission for that bucket to the app's IAM policy.",
    who: "Rick (AWS IAM). Seraphine never edits IAM.",
    infra: true,
    detail: (raw) => {
      const a = raw.match(/\bs3:[A-Za-z]+/);
      const b = raw.match(/arn:aws:s3:::[\w.-]+/);
      return [a && `permission ${a[0]}`, b && `on ${b[0]}`].filter(Boolean).join(" ");
    },
  },
  {
    id: "ssm-parameter-missing",
    test: /ParameterNotFound|SSM GetParameters? failed|GetParameters?.{0,40}(not found|failed)/i,
    what: "An AWS SSM parameter can't be read.",
    cause: "The parameter is missing (or renamed), or the role can't read it.",
    fix: "Create the parameter with the right value, or fix its name in the app's config.",
    who: "Rick (secrets). Seraphine never touches secrets or variables.",
    infra: true,
    detail: (raw) => {
      const m = raw.match(/(?:parameter|Name)[^/\n]{0,30}(\/[\w/.-]+)/i);
      return m ? `parameter ${m[1]}` : "parameter name not in the log line";
    },
  },
  {
    id: "db-connection",
    test: /ECONNREFUSED.{0,40}5432|P1001|P1017|P2024|Can't reach database server|connection (terminated|refused|timed? ?out)|timeout exceeded when trying to connect|too many clients|Connection pool timeout/i,
    what: "The API can't reach Postgres.",
    cause: "The database is down, overloaded, or the API's connection pool is exhausted.",
    fix: "Restart the API (Seraphine does this herself if /health fails), then check Postgres in Railway: CPU, connections, disk.",
    who: "Seraphine (API restart), then Ashish (Postgres)",
    infra: true,
  },
  {
    id: "cert-dns",
    test: /ENOTFOUND|EAI_AGAIN|getaddrinfo|CERT_|certificate|TLS handshake|SSL routines/i,
    what: "A DNS or security-certificate failure.",
    cause: "An address doesn't resolve or a certificate is invalid.",
    fix: "Seraphine handles this on her DNS/certificate path (puts back a changed record; never restarts for DNS or certificates).",
    who: "Seraphine",
    infra: true,
  },
  {
    id: "vendor-key-401",
    test: /\b401\b|unauthori[sz]ed|invalid[_ ]?api[_ ]?key|api[_ ]?key.{0,20}(invalid|expired|revoked)|token.{0,10}expired/i,
    also: /stripe|twilio|sendgrid|resend|postmark|openai|anthropic|bedrock|plaid|persona|docusign|google|aws|vendor|api key|apikey|x-api-key/i,
    what: "A vendor rejected our key (401).",
    cause: "The vendor key was rotated, revoked or expired.",
    fix: "Make a new key at the vendor and paste it into the service's Railway variables (key custodian, FIN-1152).",
    who: "Rick (keys). Seraphine never touches secrets or variables.",
    infra: true,
  },
  {
    id: "product-4xx",
    test: /PLAN_NOT_STARTED|ValidationError|BadRequest|\b(status|statusCode|HTTP)[=: ]?4(0[0-9]|2[0-9])\b/i,
    what: "Lots of 4xx / business-rule errors.",
    cause: "A product issue (users hitting a rule or a broken flow), not infrastructure. Restarting won't help.",
    fix: "Code fix through a PR. Seraphine opened or updated a Linear Bug.",
    who: "Ashish (Mango IT)",
    infra: false,
  },
];

export type Match = { rule: Rule; detail: string };

// Matching is plain code inside the fixer, so it may look at the raw line too
// (ports, permission names); the raw line itself never leaves the fixer.
export function matchRule(pattern: string, raw = pattern): Match | undefined {
  const hit = (re: RegExp) => re.test(pattern) || re.test(raw);
  for (const rule of RULEBOOK) {
    if (!hit(rule.test)) continue;
    if (rule.also && !hit(rule.also)) continue;
    return { rule, detail: rule.detail ? rule.detail(raw) : "" };
  }
  return undefined;
}

export function ruleText(m: Match): string {
  return `What's wrong: ${m.rule.what}${m.detail ? ` (${m.detail})` : ""}\nLikely cause: ${m.rule.cause}\nFix: ${m.rule.fix}\nWho: ${m.rule.who}`;
}
