// Everything that touches the outside world (clock, network, env, sleeping,
// logging) goes through `rt`. Production uses the real ones; tests swap in a
// fake clock and a fake network so every decision path can be checked
// without calling Railway, Better Stack, Slack or the AI gateway.

export const rt = {
  env: process.env as Record<string, string | undefined>,
  fetch: (input: string, init?: RequestInit): Promise<Response> => fetch(input, init),
  sleep: (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms)),
  now: (): number => Date.now(),
  log: (...a: unknown[]) => console.log(...a),
  error: (...a: unknown[]) => console.error(...a),
};

// When this copy of the fixer started (used by the boot guard).
export const boot = { at: Date.now() };

export const timeout = (ms: number) => AbortSignal.timeout(ms);

// "12:03" in Eastern time, for Slack and incident notes.
export function hhmm(ms: number): string {
  return new Date(ms).toLocaleTimeString("en-US", {
    timeZone: "America/New_York",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function ordinal(n: number): string {
  const s = n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] || "th";
  return `${n}${s}`;
}

export const errText = (e: any) => String(e?.message || e).slice(0, 300);
