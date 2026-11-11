// The scrubber removes ids, emails, phone numbers and anything patient-shaped.
import { describe, expect, test } from "bun:test";
import { patternOf, scrub } from "../src/scrub";

const cases: [string, string, RegExp][] = [
  ["email", "invite failed for jane.doe+test@gmail.com", /jane|gmail/],
  ["email in json", '{"to":"bob@clinic.org","status":500}', /bob|clinic\.org/],
  ["US phone dashed", "sms to 555-867-5309 failed", /867|5309/],
  ["US phone parens", "call (555) 867-5309 failed", /867|5309/],
  ["phone +1", "twilio error for +1 555 867 5309", /867|5309/],
  ["phone bare", "phone 5558675309 rejected", /5558675309/],
  ["uuid", "loan 3f2504e0-4f89-11d3-9a0c-0305e82c3301 not found", /3f2504e0/],
  ["cuid", "user clx9ab12cd34ef56gh78 missing", /clx9ab12cd34ef56gh78/],
  ["long hex", "session a1b2c3d4e5f60718 expired", /a1b2c3d4e5f60718/],
  ["numeric id", "order 48213377 failed", /48213377/],
  ["ssn", "ssn check 123-45-6789 failed", /123-45-6789/],
  ["dob iso", "dob 1984-03-12 invalid", /1984-03-12/],
  ["dob us", "born 3/12/1984 invalid", /3\/12\/1984/],
  ["patient name", "patient John Smith purge failed", /John|Smith/],
  ["title name", "Dr. Alice Wong uploaded id", /Alice|Wong/],
  ["first_name field", 'first_name="Maria" last_name=Lopez', /Maria|Lopez/],
  ["json person fields", '{"patientName":"Ann Lee","dob":"1990-01-01","memberId":"XK99"}', /Ann Lee|1990|XK99/],
  ["mrn", "mrn: 00012345 not found", /00012345/],
  ["address", "address=12 Elm Street, zip=02139", /Elm|02139/],
  ["card", "card 4111 1111 1111 1111 declined", /4111/],
  ["query string", "GET https://api.finverified.ai/v1/x?email=a@b.co&token=abc failed", /email=|abc/],
  ["bearer", "Authorization: Bearer abc.def.ghi", /abc\.def/],
  ["jwt", "token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig_part-1 bad", /eyJhbGci/],
  ["api key", "stripe sk_live_51Habcdefghijklmnop rejected", /sk_live/],
  ["aws key", "AKIAABCDEFGHIJKLMNOP denied", /AKIAABCDEFGHIJKLMNOP/],
  ["ip", "connect 10.0.4.17:5432 refused", /10\.0\.4\.17/],
];

describe("scrub removes", () => {
  for (const [name, input, leak] of cases) {
    test(name, () => {
      expect(scrub(input)).not.toMatch(leak);
    });
  }
});

describe("scrub keeps what diagnosis needs", () => {
  test("error words and codes survive", () => {
    expect(patternOf("[id-capture-retention] patient purge failed")).toBe("[id-capture-retention] patient purge failed");
    expect(patternOf("S3 AccessDenied on PutObject (HTTP 403)")).toContain("AccessDenied");
    expect(patternOf("HTTP 401 from stripe")).toContain("401");
    expect(patternOf("PLAN_NOT_STARTED")).toBe("PLAN_NOT_STARTED");
  });

  test("same problem, different ids -> same pattern", () => {
    expect(patternOf("loan 3f2504e0-4f89-11d3-9a0c-0305e82c3301 failed for a@b.co"))
      .toBe(patternOf("loan 9a7b1c2d-1111-2222-3333-444455556666 failed for z@y.org"));
  });

  test("scrubbing twice changes nothing", () => {
    for (const [, input] of cases) expect(scrub(scrub(input))).toBe(scrub(input));
  });
});
