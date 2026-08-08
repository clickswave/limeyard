# OWASP WebGoat vulnerabilities

Answer key for the **webgoat** target (OWASP WebGoat + WebWolf). The lessons state
their own objectives in the app; this document is the ground truth for maintainers
and instructors. WebGoat is upstream software, so these follow its documented
lesson set; exact lesson names shift between WebGoat versions.

> **Intentionally vulnerable. Isolated testing only.** Do not run webgoat anywhere
> it can be reached from an untrusted network.

- **App:** OWASP WebGoat (Java / Spring Boot lesson platform) + WebWolf companion
- **Start:** `./vam start webgoat`
- **URL:** `http://127.0.0.1:7003/WebGoat`
- **WebWolf:** `http://127.0.0.1:7004/WebWolf` - the out-of-band catcher: it hosts
  attacker-controlled files, logs incoming HTTP requests, and receives the mail
  WebGoat sends (used by the blind XXE, SSRF, CSRF and password-reset lessons).
- **Account:** register a local account at `/WebGoat/registration` first; lesson
  progress is tracked per user. Use the same username on WebWolf.

Status legend:

- **Live** - reachable and exploitable in the running app. (Every WebGoat lesson is Live.)

## Summary

| ID | Vulnerability | Category (OWASP Top 10) | Status |
|----|---------------|-------------------------|--------|
| WG1 | SQL injection (intro + advanced) | A03 Injection | Live |
| WG2 | Cross-site scripting (reflected / DOM) | A03 Injection | Live |
| WG3 | CSRF | A01 Broken Access Control | Live |
| WG4 | JWT weaknesses (none alg / weak key / kid) | A02 / A07 | Live |
| WG5 | XXE (incl. blind via WebWolf) | A05 / A03 | Live |
| WG6 | Path traversal | A01 Broken Access Control | Live |
| WG7 | Insecure deserialization | A08 Integrity Failures | Live |
| WG8 | IDOR | A01 Broken Access Control | Live |
| WG9 | SSRF | A10 SSRF | Live |
| WG10 | Broken authentication / reset | A07 Auth Failures | Live |
| WG11 | Vulnerable and outdated components | A06 Vulnerable Components | Live |
| WG12 | Out-of-band exploitation via WebWolf | Tooling / OOB | Live |

## Vulnerabilities

### WG1 - SQL injection

- **Where:** lessons "SQL Injection (intro)" and "SQL Injection (advanced /
  mitigation)".
- **Reproduce:** in the string-injection stage submit `Smith' OR '1'='1` to return
  every row; in the advanced stage use a `UNION`/subquery to pull all users and
  passwords, or register with a name that injects into the insert.
- **Real-world fix:** parameterized queries / prepared statements and least
  privilege; the mitigation lesson demonstrates the fixed code.

### WG2 - Cross-site scripting

- **Where:** lessons "Cross Site Scripting" and "Cross Site Scripting (stored/DOM)".
- **Reproduce:** enter `<script>alert('xss')</script>` in the reflected field (the
  fake credit-card / quantity input); for the DOM stage, discover the client-side
  route and trigger the sink with a `webgoat.customjs.phoneHome()` style payload.
- **Real-world fix:** context-aware output encoding, safe DOM APIs, and CSP.

### WG3 - CSRF

- **Where:** lesson "Cross-Site Request Forgery".
- **Reproduce:** host an HTML page on WebWolf (`7004`) that auto-submits a forged
  POST (e.g. a review or the "confirm flag" form) to the WebGoat endpoint; opening
  it while logged into WebGoat performs the action and returns your flag.
- **Real-world fix:** per-request anti-CSRF tokens, SameSite cookies, and re-checks
  of Origin/Referer.

### WG4 - JWT weaknesses

- **Where:** lesson "JWT tokens".
- **Reproduce:** decode the token; forge admin access by re-issuing it with
  `alg: none`, or crack the weak HMAC secret from a wordlist and re-sign with
  `admin: true`; later stages abuse the `kid` header (SQL/file) and the
  refresh-token flow.
- **Real-world fix:** pin a strong algorithm, reject `none`, keep secrets strong
  and server-side, and validate `kid` against an allowlist.

### WG5 - XXE

- **Where:** lesson "XXE (XML External Entity)".
- **Reproduce:** the comment endpoint parses XML; inject
  `<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]>` and reference `&e;`. For
  the blind stage, host an external DTD on WebWolf and exfiltrate the file contents
  to your WebWolf request log.
- **Real-world fix:** disable DTDs and external entities in the parser
  (`FEATURE_SECURE_PROCESSING`).

### WG6 - Path traversal

- **Where:** lesson "Path traversal".
- **Reproduce:** in the profile-image upload/retrieval stage set the filename or
  `id` to escape the directory, e.g. `..%2f..%2f..%2fetc%2fpasswd` or a
  `../` sequence that the server fails to normalize, to read files outside the
  intended folder.
- **Real-world fix:** canonicalize and validate paths against a fixed base
  directory; reject `..` segments.

### WG7 - Insecure deserialization

- **Where:** lesson "Insecure Deserialization".
- **Reproduce:** submit a crafted base64 Java serialized object to the vulnerable
  endpoint so that deserialization triggers the intended side effect (a timed delay
  / gadget), demonstrating attacker-controlled object graphs.
- **Real-world fix:** do not deserialize untrusted data; use data-only formats and
  strict type allowlists / look-ahead filtering.

### WG8 - IDOR (Insecure Direct Object References)

- **Where:** lesson "Insecure Direct Object References".
- **Reproduce:** after viewing your own profile, change the numeric object id in
  the request (or the attribute in the JSON) to read and then edit another user's
  profile you were never granted.
- **Real-world fix:** enforce per-object authorization on the server and prefer
  non-guessable identifiers.

### WG9 - SSRF

- **Where:** lesson "Server-Side Request Forgery".
- **Reproduce:** tamper the request parameter so WebGoat fetches a URL other than
  the intended one (e.g. `http://ifconfig.pro` / an internal address); the
  server-side response is reflected back, proving the server made the request.
- **Real-world fix:** allowlist outbound destinations, block internal ranges and
  metadata endpoints, and never fetch client-supplied URLs.

### WG10 - Broken authentication and password reset

- **Where:** lessons "Authentication Bypasses", "Secure Passwords", and the
  password-reset flow.
- **Reproduce:** bypass the 2FA/security-question stage by renaming or omitting the
  expected parameters; reset another user's password by answering guessable
  security questions or by intercepting the reset email in the WebWolf mailbox.
- **Real-world fix:** validate all required auth factors server-side, use expiring
  one-time reset tokens, and do not rely on static security questions.

### WG11 - Vulnerable and outdated components

- **Where:** lesson "Vulnerable Components".
- **Reproduce:** the lesson bundles a library with a known CVE (e.g. an outdated
  XStream / commons-collections); craft the documented payload for that CVE to
  reach code execution or unexpected object handling.
- **Real-world fix:** track dependencies with SCA and patch known-vulnerable
  versions promptly.

### WG12 - Out-of-band exploitation via WebWolf

- **Where:** lesson "WebWolf introduction" and any blind lesson above.
- **Reproduce:** use WebWolf at `7004` to host attacker files, catch blind XXE /
  SSRF / CSRF callbacks in its incoming-requests log, and read intercepted
  password-reset mail. It is the OAST catcher for this target.
- **Real-world fix:** not a bug in WebWolf itself; the lessons it supports each have
  their own fix above. Block egress and monitor outbound DNS/HTTP in production.

## Notes and scope

WebGoat is self-documenting: each lesson embeds its objective, hints, and often a
"solution" tab, and the WebGoat GitHub project is the upstream authority. Lesson
names above are representative and may differ by version; drive each lesson from
`/WebGoat` and use WebWolf on `7004` for the out-of-band stages. Keep this file
aligned with the version pinned in `apps/webgoat/app.yml`.
