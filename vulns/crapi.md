# crAPI vulnerabilities

Answer key for the **crapi** target (OWASP crAPI, "Completely Ridiculous API").
In the app the vulnerabilities are unlabelled; this document is for maintainers
and instructors. crAPI is upstream software, so these follow its built-in
challenge set; exact API paths can shift between crAPI versions.

> **Intentionally vulnerable. Isolated testing only.** Do not run crAPI anywhere
> it can be reached from an untrusted network.

- **App:** OWASP crAPI (Node identity + Java community + Python workshop + Postgres + Mongo)
- **Start:** `./vam start crapi --heavy` (it is heavy, ~2 GB; first boot is slow)
- **Web UI:** `http://127.0.0.1:7010` - **Mail (OTP / reset):** `http://127.0.0.1:7011` (mailhog)
- **Accounts:** register two users through the UI (an *attacker* and a *victim*)
  so cross-user access is demonstrable. Sign-up and password-reset OTPs arrive in
  mailhog. Service names below map to the three tiers: `identity`, `community`,
  `workshop`.

Status legend:

- **Live** - reachable and exploitable in the running app. (Every crAPI item is Live.)

## Summary

| ID | Vulnerability | Category (OWASP API) | Status |
|----|---------------|----------------------|--------|
| CR1 | BOLA: read another user's vehicle location | API1 Broken Object Level Authz | Live |
| CR2 | BOLA: read another user's mechanic report by id | API1 Broken Object Level Authz | Live |
| CR3 | OTP brute force resets any account's password | API2 Broken Authentication | Live |
| CR4 | JWT weaknesses (alg=none / weak key / jku) | API2 Broken Authentication | Live |
| CR5 | Excessive data exposure in the community feed | API3 Excessive Data Exposure | Live |
| CR6 | Mass assignment inflates account balance | API3 / API6 Mass Assignment | Live |
| CR7 | BFLA: call mechanic / admin-only functions | API5 Broken Function Level Authz | Live |
| CR8 | SSRF via "contact mechanic" | API7 SSRF | Live |
| CR9 | NoSQL injection in coupon validation | API8 Injection | Live |
| CR10 | No rate limiting (enables brute force / DoS) | API4 Unrestricted Resource Use | Live |

## Vulnerabilities

### CR1 - BOLA: read another user's vehicle location

- **Where:** `GET /identity/api/v2/vehicle/{vehicleId}/location`. The `vehicleId`
  (a UUID) of other users leaks via the community feed (see CR5).
- **Reproduce:** as the attacker, grab a victim's `vehicleId` from the community
  posts response, then request the location endpoint with your own token but the
  victim's `vehicleId`. It returns their GPS with no ownership check.
- **Real-world fix:** verify the object belongs to the caller before returning it.

### CR2 - BOLA: read another user's mechanic report

- **Where:** `GET /workshop/api/mechanic/mechanic_report?report_id=N`. Report ids
  are sequential.
- **Reproduce:** submit a service request to get one `report_id`, then enumerate
  nearby ids to read other users' reports.
- **Real-world fix:** authorize report ownership; use non-sequential ids.

### CR3 - OTP brute force resets any password

- **Where:** the forgot-password flow issues a short (4-digit) OTP; the verify
  endpoint (`POST /identity/api/auth/v2/check-otp`, `{email, otp, password}`)
  is not rate limited on the vulnerable version.
- **Reproduce:** trigger a reset for the victim (`POST /identity/api/auth/forget-password`),
  then brute force `0000`-`9999` against check-otp to set a new password and take
  over the account. (crAPI's `v3` OTP endpoint adds a limit; `v2` does not.)
- **Real-world fix:** rate-limit and lock OTP attempts, use longer OTPs with short
  expiry, and invalidate on too many failures.

### CR4 - JWT weaknesses

- **Where:** the identity service's JWT verification. Depending on version it
  accepts `alg: none`, a weak/guessable HMAC secret, or trusts an attacker-supplied
  `jku`/`kid`.
- **Reproduce:** decode your JWT, then forge one (alg none, or re-signed with the
  weak key) setting the `sub`/email/role to a victim or admin, and call an
  authenticated endpoint with it.
- **Real-world fix:** verify signatures with a strong asymmetric key, pin the
  algorithm, and never trust attacker-controlled `jku`/`kid`.

### CR5 - Excessive data exposure (community feed)

- **Where:** `GET /community/api/v2/community/posts/recent` returns author objects
  containing `email`, `vehicleid`, and profile fields well beyond what the UI shows.
- **Reproduce:** call it authenticated and inspect the JSON for other users' PII
  and vehicle UUIDs (which then feed CR1).
- **Real-world fix:** serialize responses with an explicit field allowlist; never
  return more than the client needs.

### CR6 - Mass assignment inflates balance

- **Where:** the coupon / credit flow (`POST /workshop/api/shop/apply_coupon`,
  `{coupon_code, amount}`) credits the account, and the credited value or reuse is
  client-influenced; profile updates also accept unexpected fields.
- **Reproduce:** apply a valid coupon repeatedly, or tamper the credited amount,
  to raise `available_credit` / balance beyond what is intended.
- **Real-world fix:** compute credit server-side, enforce single-use coupons, and
  bind updatable fields to an allowlist.

### CR7 - BFLA: mechanic / admin-only functions

- **Where:** functions meant for mechanics/admins (e.g. `POST /workshop/api/mechanic/receive_report`,
  or deleting another user's dashcam video) are reachable by a normal user token.
- **Reproduce:** call a mechanic/admin endpoint with an ordinary user's token; it
  succeeds.
- **Real-world fix:** enforce role and function-level authorization on the server.

### CR8 - SSRF via "contact mechanic"

- **Where:** `POST /workshop/api/merchant/contact_mechanic` includes a
  `mechanic_api` URL that the workshop service fetches server-side.
- **Reproduce:** set `mechanic_api` to an internal target (e.g. `http://mongodb:27017`
  or a cloud metadata address like `http://169.254.169.254/`) and observe the
  server-side request / reflected response.
- **Real-world fix:** never fetch client-supplied URLs; use an allowlist and block
  internal ranges and metadata endpoints.

### CR9 - NoSQL injection in coupon validation

- **Where:** `POST /community/api/v2/coupon/validate-coupon` validates coupon
  codes against MongoDB.
- **Reproduce:** inject a Mongo operator, e.g. `{"coupon_code": {"$ne": ""}}`, to
  bypass validation or enumerate valid coupons.
- **Real-world fix:** validate/normalize input types, reject query operators, and
  parameterize the query.

### CR10 - No rate limiting

- **Where:** OTP verification, "contact mechanic", and sign-up have no per-user or
  per-IP limits.
- **Reproduce:** high-rate requests to the OTP endpoint (this is what makes CR3
  practical) or to contact-mechanic (email flooding into mailhog / resource use).
- **Real-world fix:** per-user and per-IP rate limits, quotas, and backoff.

## Notes and scope

crAPI ships its own guided challenge list in the web UI and documents the full set
at the OWASP crAPI project. Endpoint paths above are representative and may differ
slightly by version; when in doubt, drive the flows from the UI at
`http://127.0.0.1:7010` and watch the requests. Keep this file aligned with the
crAPI version pinned in `apps/crapi/app.yml`.
