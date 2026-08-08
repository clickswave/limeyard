# OWASP Juice Shop vulnerabilities

Answer key for the **juice-shop** target (OWASP Juice Shop). In the app the
vulnerabilities are unlabelled; this document is for maintainers and instructors.
Juice Shop is upstream software, so these follow its documented challenge set;
exact routes can shift between Juice Shop versions.

> **Intentionally vulnerable. Isolated testing only.** Do not run juice-shop
> anywhere it can be reached from an untrusted network.

- **App:** OWASP Juice Shop (Node.js + Express + Angular SPA + SQLite via sql.js)
- **Start:** `./vam start juice-shop`
- **URL:** `http://127.0.0.1:7001`
- **Score Board:** `http://127.0.0.1:7001/#/score-board` - the in-app challenge
  tracker (finding it is itself the first challenge). Use it as the authoritative
  answer key.
- **Accounts:** register a user through the UI (the *attacker*). An admin account
  `admin@juice-sh.op` exists and is compromised via SQLi (JS1).

Status legend:

- **Live** - reachable and exploitable in the running app. (Every Juice Shop item is Live.)

## Summary

| ID | Vulnerability | Category (OWASP Top 10) | Status |
|----|---------------|-------------------------|--------|
| JS1 | SQLi login bypass (auth bypass, admin takeover) | A03 Injection | Live |
| JS2 | Broken access control: admin section | A01 Broken Access Control | Live |
| JS3 | IDOR: view/modify other users' baskets | A01 Broken Access Control | Live |
| JS4 | Sensitive data exposure via `/ftp` | A01 / A04 | Live |
| JS5 | Forged / unsigned JWT (alg none, weak key) | A02 / A07 | Live |
| JS6 | DOM XSS in product search | A03 Injection | Live |
| JS7 | Persisted (stored) XSS | A03 Injection | Live |
| JS8 | Broken auth: weak passwords + insecure reset | A07 Auth Failures | Live |
| JS9 | Improper input validation (basket / coupon) | A04 Insecure Design | Live |
| JS10 | SSRF via profile image URL | A10 SSRF | Live |
| JS11 | XXE via complaint file upload | A05 / A03 | Live |
| JS12 | Vulnerable and outdated components | A06 Vulnerable Components | Live |

## Vulnerabilities

### JS1 - SQL injection login bypass

- **Where:** `POST /rest/user/login`, the `email` field is concatenated into the
  SQL query.
- **Reproduce:** log in with email `' OR 1=1--` (any password), which returns the
  first user in the table (the administrator). `admin@juice-sh.op'--` targets a
  specific account.
- **Real-world fix:** use parameterized queries / prepared statements; never build
  SQL by string concatenation.

### JS2 - Broken access control: admin section

- **Where:** the Angular route `/#/administration` and its backing API
  (`GET /rest/admin/application-configuration`, `GET /api/Users`).
- **Reproduce:** authenticate as admin (via JS1) or forge an admin JWT (JS5), then
  browse to `/#/administration` to view all registered users and feedback. Direct
  API calls also succeed without the UI.
- **Real-world fix:** enforce server-side role checks on every admin route and API,
  not just by hiding the client-side link.

### JS3 - IDOR: view and modify other users' baskets

- **Where:** `GET /rest/basket/{id}` and the basket item endpoints trust the `id`
  in the URL rather than the caller's identity.
- **Reproduce:** log in, note your basket id, then request `/rest/basket/1`,
  `/rest/basket/2`, etc. (or replay a checkout with another basket id) to read and
  alter another user's cart.
- **Real-world fix:** verify the basket belongs to the authenticated user before
  returning or mutating it.

### JS4 - Sensitive data exposure via `/ftp`

- **Where:** the static `/ftp` directory is browsable at
  `http://127.0.0.1:7001/ftp`. Only `.md` and `.pdf` are meant to be served.
- **Reproduce:** `GET /ftp/legal.md` works directly. Confidential files
  (`acquisitions.md`, `coupons_2013.md.bak`, `package.json.bak`) are pulled by
  bypassing the extension filter with a poison null byte, e.g.
  `/ftp/coupons_2013.md.bak%2500.md`.
- **Real-world fix:** do not expose a file directory over HTTP; enforce
  allowlists on the fully-decoded path and store secrets outside the web root.

### JS5 - Forged / unsigned JWT

- **Where:** the session JWT is signed with RS256, but the app also accepts
  `alg: none` and the RSA private key ships in the source tree.
- **Reproduce:** decode your token, change the payload `email` to
  `jwtn3d@juice-sh.op` (or the admin), re-issue it with `alg: none` (or re-sign
  with the bundled key), and call an authenticated endpoint with the forged token.
- **Real-world fix:** pin the algorithm, reject `none`, keep signing keys secret,
  and verify signatures server-side.

### JS6 - DOM XSS in product search

- **Where:** the search box binds the `q` parameter into the DOM without
  sanitization (`/#/search?q=`).
- **Reproduce:** search for
  `<iframe src="javascript:alert(\`xss\`)">` (or navigate to
  `/#/search?q=<iframe src="javascript:alert(\`xss\`)">`); the payload executes.
- **Real-world fix:** treat all user input as untrusted, bind via safe framework
  APIs, and apply a strict Content-Security-Policy.

### JS7 - Persisted (stored) XSS

- **Where:** several fields persist markup that is later rendered without escaping
  (e.g. a product created via `POST /api/Products` with script in the name, or the
  user profile / comment fields that bypass the client sanitizer).
- **Reproduce:** submit `<iframe src="javascript:alert(\`xss\`)">` through the API
  path that skips the Angular sanitizer; it runs whenever the record is displayed.
- **Real-world fix:** output-encode on render, sanitize on input server-side, and
  enforce CSP.

### JS8 - Broken auth: weak passwords and insecure reset

- **Where:** admin uses a weak, guessable password; the forgot-password flow
  (`/#/forgot-password`) authenticates users with a single security question.
- **Reproduce:** brute force the admin password (`admin123`), or reset the account
  of Jim / Bender / the admin by answering their guessable security question
  ("Your eldest sibling's middle name?", etc.) to set a new password.
- **Real-world fix:** enforce password strength and lockout; do not use static
  security questions as a sole reset factor; use expiring one-time reset tokens.

### JS9 - Improper input validation

- **Where:** the basket and checkout flow does not validate quantities or coupon
  values server-side.
- **Reproduce:** set a basket item quantity to a negative number to distort the
  total, apply an expired or forged coupon, or place an order you cannot afford.
- **Real-world fix:** validate and re-compute all order values server-side; reject
  out-of-range and tampered inputs.

### JS10 - SSRF via profile image URL

- **Where:** the profile page lets you set an avatar by URL
  (`POST /profile/image/url`), which the server fetches.
- **Reproduce:** supply an internal or metadata URL that the browser could not
  reach; the server-side fetch performs the request, confirming SSRF.
- **Real-world fix:** never fetch client-supplied URLs; use an allowlist and block
  internal ranges and metadata endpoints.

### JS11 - XXE via complaint file upload

- **Where:** the complaint page (`/#/complain`) file upload (`POST /file-upload`)
  parses uploaded XML.
- **Reproduce:** upload an `.xml` file declaring an external entity, e.g.
  `<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>`, and observe
  file contents / server delay (blind XXE via an external DTD to an OAST host).
- **Real-world fix:** disable external entities and DTDs in the XML parser
  (`FEATURE_SECURE_PROCESSING`), and prefer non-XML formats.

### JS12 - Vulnerable and outdated components

- **Where:** `package.json` intentionally pins libraries with known CVEs (e.g.
  outdated `sanitize-html`, `jsonwebtoken`, `express-jwt`, and typosquatted deps).
- **Reproduce:** the Score Board's "Legacy" / "Supply Chain" challenges exercise
  these; a dependency scan flags the vulnerable versions.
- **Real-world fix:** track dependencies with SCA, patch promptly, and remove
  unmaintained or typosquatted packages.

## Notes and scope

Juice Shop ships its own authoritative answer key: the in-app **Score Board** at
`/#/score-board` enumerates every challenge, and the companion guide "Pwning OWASP
Juice Shop" (pwning.owasp-juice.shop) documents solutions in full. Routes above
are representative and may differ by version; drive flows from the UI and watch
the requests. Keep this file aligned with the Juice Shop version pinned in
`apps/juice-shop/app.yml`.
