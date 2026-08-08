# FaultLine ISP vulnerabilities

Answer key for the **faultline** target. In the app the vulnerabilities are
unlabelled on purpose, so a tester has to discover them. This document is for
maintainers and instructors.

> Source of truth: this mirrors `vulns.md` in the faultline repo
> (github.com/clickswave/faultline). If they drift, that file wins.

> **Intentionally vulnerable. Isolated testing only.** Every item below is
> deliberate. Do not "fix" them, and do not run the app anywhere it can be
> reached from an untrusted network.

- **App:** FaultLine ISP (SvelteKit + Rust API + Postgres + Redis)
- **Start:** `./vam start faultline` (the manager clones it from GitHub on first run)
- **Base URL:** `http://127.0.0.1:8088` (all API paths under `/api/v1`)
- **Demo accounts (seeded, plaintext):** `alice@example.com` / `password`
  (customer, user id 3, account `FL-100001`) and `admin@faultline.local` / `admin`.

Status legend:

- **Live** - reachable and exploitable through the endpoints that exist today.
- **Seeded** - planted in the database or schema, but no current endpoint or
  render path reaches it yet (the API implements a subset of the full design).

## Summary

| ID | Vulnerability | Category | Status |
|----|---------------|----------|--------|
| H1 | Plaintext password storage and comparison | Authentication | Live |
| D12 | No account lockout or throttling (app layer) | Authentication | Live |
| C5 | PII and secret leakage (SSN, API key, password) | Data exposure | Live |
| A1 | Broken object-level authorization (BOLA / IDOR) | Access control | Live |
| J3 | Permissive CORS (reflected origin + credentials) | Misconfiguration | Live |
| C6 | Full payment-card token stored and leakable | Data exposure | Seeded |
| E10 | Stored XSS payload in support tickets | Injection | Seeded |
| E11 | Stored XSS via device nickname | Injection | Seeded |
| I1 | Coupon flow abuse (`max_uses` ignored) | Business logic | Seeded |
| H2 | Weak/unsalted hash variant noted in seed | Authentication | Seeded |

Live: 5. Seeded: 5. Total tagged: 10.

## Live vulnerabilities

### H1 - Plaintext password storage and comparison

- **Where:** `deploy/api/src/main.rs` (register stores the password as-is into
  `users.password_hash`; login does a direct string comparison). `deploy/db/seed.sql`
  seeds passwords in plaintext.
- **Reproduce:** log in as `alice@example.com` / `password`. The stored value is
  the literal password, and it is also readable through the leaks below.
- **Real-world fix:** hash with a slow, salted algorithm (argon2id or bcrypt) and
  verify in constant time. Never store or return the raw password.

### D12 - No account lockout or throttling

- **Where:** the login handler tracks no failed attempts and never locks or backs
  off. The only limit is volumetric, at the nginx edge.
- **Reproduce:** send many `POST /api/v1/auth/login` attempts for one account;
  within a normal request rate none are refused, so credentials can be brute
  forced.
- **Real-world fix:** lock or exponentially back off after N failures per account
  and per IP; add CAPTCHA or step-up on anomalies.

### C5 - PII and secret leakage

- **Where:** `GET /api/v1/admin/users` returns `ssn` and `apiKey` for every user.
  `GET /api/v1/users/:id` returns the full user row, including `ssn`, `apiKey`,
  the plaintext password, and balance.
- **Reproduce:** as admin, `GET /api/v1/admin/users` returns SSNs and API keys.
  As any logged-in user, `GET /api/v1/users/3` returns alice's SSN, API key, and
  password.
- **Real-world fix:** never select sensitive columns into responses; use explicit
  field allowlists; separate admin views with least privilege.

### A1 - Broken object-level authorization (BOLA / IDOR)

- **Where:** `GET /api/v1/users/:id` performs no ownership or role check, and user
  ids are sequential. Account numbers (`FL-1000NN`) are sequential too.
- **Reproduce:** log in as alice (id 3), then request `GET /api/v1/users/1`,
  `/2`, `/4`, and so on to read other users' full records.
- **Real-world fix:** enforce that the caller may access the object (ownership or
  role), and prefer non-guessable identifiers.

### J3 - Permissive CORS

- **Where:** the API's CORS layer reflects the request `Origin`, sets
  `Access-Control-Allow-Credentials: true`, and allows all methods and headers.
- **Reproduce:** a page on any origin can make credentialed cross-origin requests
  to the API and read the responses, enabling cross-site data theft.
- **Real-world fix:** allowlist specific trusted origins, and never combine a
  reflected origin with credentialed requests.

## Seeded vulnerabilities (not reachable yet)

Present in the data or schema but the current API does not expose a path to them.
Wiring one endpoint or an unescaped render turns each into a Live item.

- **C6 - Payment-card token leak.** `payment_methods.token` holds a full card
  token. The billing and payment-methods endpoints deliberately omit it today.
- **E10 - Stored XSS in tickets.** A support ticket is seeded with
  `<img src=x onerror=...>` in `tickets.body_html`. No tickets endpoint/view
  renders it yet.
- **E11 - Stored XSS via device nickname.** Device nicknames are a stored-XSS
  sink, but the devices page renders them escaped (Svelte escapes by default, no
  `@html`), so the payload does not execute.
- **I1 - Coupon flow abuse.** The `coupons` table includes `FREEMONTH` with
  `max_uses = 1`; the intended bug is that redemption ignores `max_uses`. No
  redemption endpoint yet.
- **H2 - Weak hash variant.** The seed notes an unsalted/weak-hash idea for some
  accounts. Moot while every password is stored in plaintext (H1).

## Notes and scope

The IDs come from a larger intended catalog (categories A through L plus
API-specific issues: file uploads, missing security headers, unrestricted
resource consumption, GraphQL introspection, and more), most of which is not
implemented. The current app is a subset: five vulnerabilities are exploitable
end to end, five more are seeded in the data.

If you extend the API, keep new bugs unlabelled in the UI and add them here with
an ID, a location, a reproduction, and the real-world fix.
