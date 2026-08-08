# VAmPI vulnerabilities

Answer key for the **vampi** target (VAmPI, the Vulnerable API). The endpoints are
unlabelled in the app; this document is for maintainers and instructors. VAmPI is
upstream software, so these follow its documented OWASP API Top 10 mapping. This
fleet runs it in **vulnerable mode** (`vulnerable=1`), so the insecure code paths
are active.

> **Intentionally vulnerable. Isolated testing only.** Do not run vampi anywhere it
> can be reached from an untrusted network.

- **App:** VAmPI (Python / Flask REST API + SQLite), OWASP API Top 10 demo
- **Start:** `./vam start vampi`
- **URL:** `http://127.0.0.1:7005`
- **Setup:** `GET /createdb` (re)seeds the demo users and books - call it before
  testing. Set env `vulnerable=0` for the secured baseline.
- **Auth:** `POST /users/v1/login` returns a JWT; send it as
  `Authorization: Bearer <token>` on protected routes.

Status legend:

- **Live** - reachable and exploitable in the running app. (Every VAmPI item is Live.)

## Summary

| ID | Vulnerability | Category (OWASP API) | Status |
|----|---------------|----------------------|--------|
| VP1 | Excessive data exposure via `_debug` | API3 Excessive Data Exposure | Live |
| VP2 | BOLA: read any user by username | API1 Broken Object Level Authz | Live |
| VP3 | Mass assignment to create an admin | API6 Mass Assignment | Live |
| VP4 | Broken auth / weak JWT secret | API2 Broken Authentication | Live |
| VP5 | Unauthorized email update | API1 / API5 | Live |
| VP6 | Unauthorized password update | API1 / API5 | Live |
| VP7 | No rate limiting | API4 Unrestricted Resource Use | Live |
| VP8 | SQL injection in lookups | API8 Injection | Live |
| VP9 | BOLA: read another user's book secret | API1 Broken Object Level Authz | Live |
| VP10 | BFLA: admin-only user delete | API5 Broken Function Level Authz | Live |

## Vulnerabilities

### VP1 - Excessive data exposure via debug endpoint

- **Where:** `GET /users/v1/_debug`.
- **Reproduce:** call it unauthenticated; it returns every user object including
  `username`, `email`, `admin` flag, and the **plaintext password**.
- **Real-world fix:** remove debug endpoints from production and never serialize
  secret columns; use explicit field allowlists.

### VP2 - BOLA: read any user by username

- **Where:** `GET /users/v1/{username}`.
- **Reproduce:** request `GET /users/v1/admin` (or any username enumerated from
  VP1) and read that account's email and admin status with no ownership check.
- **Real-world fix:** authorize that the caller may view the requested object;
  return only the caller's own record unless privileged.

### VP3 - Mass assignment to create an admin

- **Where:** `POST /users/v1/register`.
- **Reproduce:** register with an extra field, e.g.
  `{"username":"attacker","password":"x","email":"a@b.c","admin":true}`; the
  `admin` flag is bound straight from the body, creating an administrator.
- **Real-world fix:** bind only an allowlist of client-settable fields; never map
  privilege flags from request input.

### VP4 - Broken authentication / weak JWT secret

- **Where:** `POST /users/v1/login` issues a JWT signed with a hardcoded/weak HMAC
  secret.
- **Reproduce:** log in, decode the token, then forge one with the known secret
  setting the `sub`/username to `admin` (or set `admin` semantics), and use it on
  protected routes.
- **Real-world fix:** sign with a strong secret kept server-side (or asymmetric
  keys), pin the algorithm, and short-lived tokens.

### VP5 - Unauthorized email update

- **Where:** `PUT /users/v1/{username}/email`.
- **Reproduce:** in vulnerable mode the endpoint acts on the username in the path
  rather than the token's identity, so a valid token can change another user's
  email (or is accepted with a malformed token).
- **Real-world fix:** derive the target user from the authenticated token, not the
  URL, and re-verify authorization.

### VP6 - Unauthorized password update

- **Where:** `PUT /users/v1/{username}/password`.
- **Reproduce:** as above, supply a body like `{"password":"newpass"}` for another
  user's username to reset their password and take over the account.
- **Real-world fix:** require the current password, act only on the token's own
  identity, and rate-limit.

### VP7 - No rate limiting

- **Where:** `POST /users/v1/login` and `POST /users/v1/register` (all endpoints).
- **Reproduce:** send unlimited login attempts to brute force a password, or spam
  registration; no throttle or lockout applies.
- **Real-world fix:** per-user and per-IP rate limits, lockout, and backoff.

### VP8 - SQL injection in lookups

- **Where:** the username / book lookups build queries by string concatenation in
  vulnerable mode (`GET /users/v1/{username}`, `GET /books/v1/{title}`).
- **Reproduce:** inject through the path/parameter, e.g. a value containing
  `' OR '1'='1`, to bypass the intended filter or extract extra rows.
- **Real-world fix:** parameterized queries / ORM binding for every input.

### VP9 - BOLA: read another user's book secret

- **Where:** `GET /books/v1/{book_title}`.
- **Reproduce:** each book has a `secret` owned by a user; request another user's
  book title and the response returns its secret with no ownership check.
- **Real-world fix:** authorize object ownership before returning per-object
  secrets.

### VP10 - BFLA: admin-only user delete

- **Where:** `DELETE /users/v1/{username}` is meant to be admin-only.
- **Reproduce:** forge an admin token (VP4) or register an admin (VP3), then delete
  arbitrary users - a function-level authorization failure.
- **Real-world fix:** enforce role checks server-side on privileged functions,
  independent of any client-supplied claim.

## Notes and scope

VAmPI's authoritative answer key is its project README
(github.com/erev0s/VAmPI), which maps each endpoint to the OWASP API Security Top
10 and documents the `vulnerable` flag. The `/ui` Swagger page enumerates every
route. Set `vulnerable=0` to compare against the secured baseline. Keep this file
aligned with the version pinned in `apps/vampi/app.yml`.
