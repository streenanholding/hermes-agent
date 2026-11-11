// Scrubber: runs on every error line before it becomes a pattern, a Slack
// post, a Linear Bug or a model prompt. Removes ids, emails, phone numbers,
// keys and anything patient-shaped (names, dates of birth, member ids,
// addresses). When unsure, it removes.

const PERSON_KEYS =
  "first_?name|last_?name|full_?name|patient_?name|given_?name|family_?name|name|dob|date_?of_?birth|birth_?date|ssn|mrn|member_?id|subscriber_?id|policy_?(?:number|id)|insurance_?id|address|street|city|zip|postal_?code|phone|mobile|email|patient|clinic_?patient";

const RULES: [RegExp, string][] = [
  // keys and tokens
  [/\bBearer\s+[A-Za-z0-9._~+/=-]+/gi, "Bearer <key>"],
  [/\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g, "<jwt>"],
  [/\b(?:sk|pk|rk|xox[abp])[-_][A-Za-z0-9_-]{10,}/g, "<key>"],
  [/\bAKIA[0-9A-Z]{16}\b/g, "<key>"],
  // emails
  [/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, "<email>"],
  // URLs keep host and path, never the query string
  [/(https?:\/\/[^\s?#"']+)\?[^\s"']*/g, "$1?<query>"],
  // person fields written as key=value or "key": "value" (unquoted values run
  // to the next comma or the next key, so "address=12 Elm Street" goes whole)
  [new RegExp(`(["']?\\b(?:${PERSON_KEYS})\\b["']?\\s*[:=]\\s*)("[^"]*"|'[^']*'|(?:(?!\\s+\\w+\\s*[:=])[^,;}&\\n"])+)`, "gi"), "$1<redacted>"],
  // "patient John Smith", "member Jane"
  [/\b(patient|member|customer|borrower|applicant|user|client)\s+[A-Z][a-z'-]+(?:\s+[A-Z][a-z'-]+)*/g, "$1 <person>"],
  [/\b(?:Mr|Mrs|Ms|Dr|Miss)\.?\s+[A-Z][a-z'-]+(?:\s+[A-Z][a-z'-]+)?/g, "<person>"],
  // ids
  [/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, "<id>"],
  [/\b[0-9a-f]{12,}\b/gi, "<id>"],
  [/\b(?=[A-Za-z0-9_-]*\d)(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]{16,}\b/g, "<id>"],
  // numbers that identify people
  [/\b\d{3}-\d{2}-\d{4}\b/g, "<ssn>"],
  [/\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?Z?)?\b/g, "<date>"],
  [/\b\d{1,2}\/\d{1,2}\/\d{2,4}\b/g, "<date>"],
  [/(?<![\w#])(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?!\w)/g, "<phone>"],
  [/\b\d{1,3}(?:\.\d{1,3}){3}\b/g, "<ip>"],
  [/\b(?:\d[ -]?){12,18}\d\b/g, "<number>"],
  [/\b\d{4,}\b/g, "#"],
];

export function scrub(text: string): string {
  let s = String(text ?? "");
  for (const [re, to] of RULES) s = s.replace(re, to);
  return s;
}

// The pattern of an error line: scrubbed, ids stripped, whitespace collapsed.
// The same problem always gives the same pattern, which is what the AI cache
// and the Slack thread key use.
export function patternOf(text: string): string {
  return scrub(text).replace(/\s+/g, " ").trim().slice(0, 300);
}
