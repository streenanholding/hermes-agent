// What Seraphine watches and the fixed numbers she works by.
// Ids here are Railway project/environment/service ids, not secrets.
// Keys and tokens live only in Railway variables (see README.md).

// ---- The 4-minute window (do not remove) ----
// Every Better Stack incident goes to the fixer first. The "FinVerified Sev-1"
// policy waits 4 minutes before calling people, so she can confirm, repair
// and verify. If she fixes it and sees it healthy twice, she acknowledges and
// resolves the incident and the call never goes out. If not, people are
// called at minute 4. Decided Oct 16 2026 (FIN-937). Never set it to 0.
export const WINDOW_MS = 4 * 60_000;
export const HEALTHY_CHECKS = 2; // consecutive healthy checks before she silences anything
export const CHECK_GAP_MS = 15_000;
export const SETTLE_MS = 20_000; // give a restart/rollback this long before the first check
export const VERIFY_BUDGET_MS = 120_000; // after an action, how long she waits for 2 healthy checks
export const RECENT_FIX_MS = 10 * 60_000; // an alert for something she fixed this recently gets closed too

export const MAX_ACTIONS_PER_HOUR = 2;
export const ROLLBACK_WINDOW_MIN = 120;
export const THREAD_WINDOW_MS = 6 * 3_600_000; // same problem within 6 h updates one Slack thread
export const PATROL_MS = 5 * 60_000;

export type Target = {
  name: string;
  projectId: string;
  environmentId: string;
  serviceId: string;
  tokenVar: string;
  healthUrl: string;
  allowRollback: boolean;
  match: string[]; // exact hostnames only
  okBelow500?: boolean; // any answer under 500 counts as "up" (used where the exact health path is unverified)
  drill?: boolean; // staging target used only by the monthly drill
};

export const AGENT_PROJECT = "b5592ad0-6a97-4d8c-b7a4-bf8a2f285f47";
export const AGENT_ENV = "150daae5-a2f0-4c52-894e-84f60fca8fde";
export const APP_SERVICE_WEB = "46889cf7-00b4-4040-9575-6f940aaf33ec";

export const TARGETS: Target[] = [
  {
    name: "Platform API (api.finverified.ai)",
    projectId: "b00697ce-eec6-4268-9080-b70a8ee85176",
    environmentId: "f4709c5c-1d75-4e30-b02f-f06059512cb3",
    serviceId: "f1196a49-9cf1-467c-992c-c0ad3ebef78a",
    tokenVar: "RAILWAY_TOKEN_APP",
    healthUrl: "https://api.finverified.ai/health",
    allowRollback: false, // DB migrations make code rollback unsafe: restart only
    match: ["api.finverified.ai", "finverified-app-production.up.railway.app"],
  },
  {
    name: "Platform web (app.finverified.ai)",
    projectId: "b00697ce-eec6-4268-9080-b70a8ee85176",
    environmentId: "f4709c5c-1d75-4e30-b02f-f06059512cb3",
    serviceId: APP_SERVICE_WEB,
    tokenVar: "RAILWAY_TOKEN_APP",
    healthUrl: "https://app.finverified.ai",
    allowRollback: true,
    match: ["app.finverified.ai", "finverified-web-test-production.up.railway.app"],
  },
  {
    name: "Advisor Sandbox (sandbox.finverified.ai)",
    projectId: "77c5be8f-a4c8-409a-9323-ef25398f00af",
    environmentId: "b4956758-7c25-42ef-8def-3c889089f958",
    serviceId: "808545a2-88dd-457f-a656-508e61ef4c90",
    tokenVar: "RAILWAY_TOKEN_SANDBOX",
    healthUrl: "https://sandbox.finverified.ai",
    allowRollback: true,
    match: ["sandbox.finverified.ai", "sandbox-web-sandbox-0726.up.railway.app"],
  },
  {
    name: "Advisor walkthrough (walkthrough.finverified.ai)",
    projectId: "2326ad7a-d644-45f1-b602-07dc7288db48",
    environmentId: "3a4ea6cb-df98-479e-8af0-e0cb44d3ee8c",
    serviceId: "686afe20-b6b2-4bb0-a2d9-c19e7e822d1a",
    tokenVar: "RAILWAY_TOKEN_WALKTHROUGH",
    healthUrl: "https://walkthrough.finverified.ai",
    allowRollback: true,
    match: ["walkthrough.finverified.ai", "walkthrough-production-b080.up.railway.app"],
  },
  {
    name: "Partner Academy (academy.finverified.ai)",
    projectId: "ff743c4b-d40c-4a4c-b581-3abc4614b666",
    environmentId: "23dac866-c961-4a3f-887a-e0dee9330bf0",
    serviceId: "1d4dc733-28f3-4fb7-9e74-8cb874958e06",
    tokenVar: "RAILWAY_TOKEN_ACADEMY",
    healthUrl: "https://academy.finverified.ai/health",
    allowRollback: true,
    match: ["academy.finverified.ai", "finverified-academy.up.railway.app"],
  },
  {
    name: "Website (finverified.ai)",
    projectId: "b29288a0-8c0a-422e-a912-933ca840889b",
    environmentId: "4fb518a3-93a6-4e27-90dd-481bea495577",
    serviceId: "258eba89-0f98-43ec-b632-e5fd261150a8",
    tokenVar: "RAILWAY_TOKEN_WEBSITE",
    healthUrl: "https://finverified.ai",
    allowRollback: true,
    match: ["www.finverified.ai", "finverified.ai", "finverified-website-production.up.railway.app"],
  },
  {
    name: "AI gateway (LiteLLM — every agent's brain goes through it)",
    projectId: AGENT_PROJECT,
    environmentId: AGENT_ENV,
    serviceId: "9cbc81de-0ada-491e-8e47-3c764dbc6bfc",
    tokenVar: "RAILWAY_TOKEN_AGENTS",
    healthUrl: "https://litellm-gateway-production-774e.up.railway.app/health/liveliness",
    allowRollback: false,
    match: ["litellm-gateway-production-774e.up.railway.app"],
    okBelow500: true,
  },
];

// Every production environment id. The drill refuses to touch any of these.
export const PRODUCTION_ENVS = new Set([...TARGETS.map((t) => t.environmentId), AGENT_ENV]);

export const WEBSITE_NAME = "Website (finverified.ai)";
export const WATCHED_SUFFIXES = ["finverified.ai", "up.railway.app"];
export const FIXER_HOST = "seraphine-fixer-production.up.railway.app";

// Services with no web address (they dial out to Slack/Telegram). Checked by
// asking Railway whether the running copy has CRASHED. Restart only.
export type StatusTarget = { name: string; serviceId: string };
export const STATUS_TARGETS: StatusTarget[] = [
  { name: "Sol (CFO agent)", serviceId: "d37c0687-9282-49d1-abab-56103c1a8e70" },
  { name: "Carly (Chief of Staff agent)", serviceId: "c6055e21-cb61-469c-b9a2-1a9f7b6b7ff5" },
  { name: "Seraphine's Slack brain (hermes-seraphine)", serviceId: "087ecb34-8f2f-49f0-a5aa-1cda82b39a1f" },
  { name: "Agent database (pgvector-db)", serviceId: "6e7feead-083a-4f0f-9cbf-d630b60c542e" },
];
export const asTarget = (s: StatusTarget): Target => ({
  name: s.name, projectId: AGENT_PROJECT, environmentId: AGENT_ENV, serviceId: s.serviceId,
  tokenVar: "RAILWAY_TOKEN_AGENTS", healthUrl: "", allowRollback: false, match: [],
});

// Sites whose DNS alerts are check-only (never restarted from a DNS alert).
export const CHECK_ONLY: Record<string, string> = {
  "walkthrough.finverified.ai": "https://walkthrough.finverified.ai",
  "academy.finverified.ai": "https://academy.finverified.ai/health",
};

// Key pages checked when an alert names no host (Playwright / error alerts).
const APP_WEB = "https://app.finverified.ai";
export const JOURNEYS = [
  `${APP_WEB}/`, `${APP_WEB}/login`, `${APP_WEB}/register`, `${APP_WEB}/waitlist`,
  `${APP_WEB}/compliance/check`, `${APP_WEB}/free-tools`, `${APP_WEB}/lender/login`,
  "https://api.finverified.ai/health", "https://finverified.ai/",
];

// ---- Blind-spot watch defaults (override with variables, see README) ----
// Production log sources in Better Stack (SQL table prefix). Since Oct 27 the
// app logs to finverified_app_oct27; the old finverified_app_production went
// silent that day and is no longer watched.
export const DEFAULT_PROD_SOURCES = "t534306_finverified_app_oct27";
export const DEFAULT_LOG_SILENCE_MIN = 30;
export const DEFAULT_SMOKE_REPO = "RHE-LLC/FinVerified.ai";
export const DEFAULT_SMOKE_WORKFLOW = "e2e-prod-smoke.yml";
export const CERT_RENEW_ALARM_DAYS = 20; // auto-renew normally happens at 30 days left
export const DEFAULT_UPTIME_TARGET = 99.99;

// Linear team "FinVerified".
export const DEFAULT_LINEAR_TEAM = "66542299-c014-4e13-b4b1-c5ec469fbb73";

export const LITELLM_DEFAULT = "https://litellm-gateway-production-774e.up.railway.app";
export const AI_FAST = "seraphine-fast";
export const AI_STRONG = "seraphine-strong";
export const DEFAULT_AI_CAP_USD = 25; // Seraphine's weekly LiteLLM cap (AGENTS.md section 11)
