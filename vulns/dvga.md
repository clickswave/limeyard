# DVGA vulnerabilities

Answer key for the **dvga** target (Damn Vulnerable GraphQL Application). The
issues are unlabelled in the app; this document is for maintainers and
instructors. DVGA is upstream software, so these follow its documented solution
set; some paths change between the Beginner and Expert difficulty modes.

> **Intentionally vulnerable. Isolated testing only.** Do not run dvga anywhere it
> can be reached from an untrusted network.

- **App:** Damn Vulnerable GraphQL Application (Python / Flask + Graphene + SQLite)
- **Start:** `./vam start dvga`
- **URL:** `http://127.0.0.1:7006/graphql` - GraphiQL / Altair explorer UI. All
  operations go to `POST http://127.0.0.1:7006/graphql`; live subscriptions use
  `/subscriptions` (WebSocket).
- **Mode:** toggle **Beginner (easy)** vs **Expert (hard)** in the top bar; Expert
  adds partial filtering/obfuscation. Payloads below assume Beginner.

Status legend:

- **Live** - reachable and exploitable in the running app. (Every DVGA item is Live.)

## Summary

| ID | Vulnerability | Category | Status |
|----|---------------|----------|--------|
| DG1 | Introspection enabled (schema dump) | Information Disclosure | Live |
| DG2 | Denial of service (nesting / batching) | Unrestricted Resource Use | Live |
| DG3 | OS command injection | Injection | Live |
| DG4 | SQL / code injection | Injection | Live |
| DG5 | IDOR: read other users' pastes | Broken Access Control | Live |
| DG6 | Information disclosure (errors / diagnostics) | Information Disclosure | Live |
| DG7 | Authentication bypass | Broken Authentication | Live |
| DG8 | Batching brute force (login / OTP) | Broken Authentication | Live |
| DG9 | CSRF via GET-based GraphQL | Broken Access Control | Live |
| DG10 | No rate limiting | Unrestricted Resource Use | Live |
| DG11 | Stored XSS via paste content | Injection (XSS) | Live |

## Vulnerabilities

### DG1 - Introspection enabled

- **Where:** the `/graphql` schema; introspection is not disabled.
- **Reproduce:** send the standard introspection query
  (`query { __schema { types { name fields { name } } queryType { name }
  mutationType { name } } }`) to dump every type, query, and mutation, including
  the sensitive ones (`systemUpdate`, `importPaste`, `deleteAllPastes`).
- **Real-world fix:** disable introspection in production and hide the schema
  behind auth.

### DG2 - Denial of service

- **Where:** query planner has no depth or cost limit; the endpoint also accepts
  batched query arrays.
- **Reproduce:** send a deeply nested / circular query (`pastes { owner { pastes {
  owner { pastes { ... } } } } }`), or a batch of thousands of aliased operations in
  one request; the server exhausts resources.
- **Real-world fix:** enforce query depth/complexity/cost limits, disable or cap
  batching, and set timeouts.

### DG3 - OS command injection

- **Where:** the `systemUpdate` mutation and the `importPaste` mutation (which
  fetches a URL and passes it to a shell).
- **Reproduce:** `mutation { importPaste(host:"localhost", port:80, path:"/",
  scheme:"http") { result } }` with an injected `;id`-style value in a shell-passed
  field, or invoke `systemUpdate`, to run OS commands (RCE).
- **Real-world fix:** never pass input to a shell; use argument arrays with no
  shell and strict input validation.

### DG4 - SQL / code injection

- **Where:** paste lookups/filters (`paste(id: ...)`, `pastes(filter: ...)`) build
  raw SQL.
- **Reproduce:** inject a SQL fragment through the `filter`/`id` argument (e.g. a
  value containing `' OR '1'='1`) to return rows you should not see or alter the
  query.
- **Real-world fix:** parameterize all queries and validate argument types.

### DG5 - IDOR: read other users' pastes

- **Where:** `paste(id: N)` and `pastes` return private pastes regardless of the
  `public`/`ownerId` fields.
- **Reproduce:** enumerate `query { paste(id: 1) { content owner { name } } }`,
  `id: 2`, etc. to read private pastes belonging to other users.
- **Real-world fix:** enforce per-object authorization; filter by the
  authenticated owner and honor the `public` flag.

### DG6 - Information disclosure

- **Where:** verbose GraphQL error messages, the `systemDiagnostics` /
  `systemHealth` fields, and server metadata via `__typename` / stack traces.
- **Reproduce:** send a malformed query to get stack traces, or query diagnostic
  fields to leak server version, config, and internal state.
- **Real-world fix:** return generic errors, disable debug mode, and remove
  diagnostic fields from the public schema.

### DG7 - Authentication bypass

- **Where:** the `login` mutation and the paste-creation flow accept requests
  without enforcing a valid session; the `X-DVGA-MODE` header and `me` query expose
  state.
- **Reproduce:** create/read pastes and reach protected operations without a valid
  token, or manipulate the mode header to change enforcement.
- **Real-world fix:** require and verify authentication server-side on every
  protected resolver.

### DG8 - Batching brute force

- **Where:** GraphQL query batching bypasses per-request throttling on `login` /
  OTP checks.
- **Reproduce:** send one HTTP request containing an array of many aliased `login`
  (or 2FA/OTP verify) mutations, each with a different guess, to brute force
  credentials in a single round trip.
- **Real-world fix:** disable batching or count each operation toward the limit;
  rate-limit and lock authentication attempts.

### DG9 - CSRF via GET-based GraphQL

- **Where:** `/graphql` accepts operations over `GET` with a `query` parameter.
- **Reproduce:** a cross-site `GET /graphql?query=mutation{createPaste(...)}` (or an
  `<img>`/link) executes a mutation using the victim's session.
- **Real-world fix:** reject state-changing operations over GET, require a
  CSRF token / custom header, and use SameSite cookies.

### DG10 - No rate limiting

- **Where:** all resolvers; no per-client throttle.
- **Reproduce:** repeated logins or expensive queries run unbounded (this is what
  makes DG2 and DG8 practical).
- **Real-world fix:** per-client rate limits, cost budgets, and backoff.

### DG11 - Stored XSS via paste content

- **Where:** paste `title` / `content` is stored and later rendered unescaped on
  the public pastes page.
- **Reproduce:** `mutation { createPaste(title:"x",
  content:"<script>alert(1)</script>", public:true) { paste { id } } }`; the script
  fires when the public pastes view renders it.
- **Real-world fix:** output-encode on render and sanitize stored HTML.

## Notes and scope

DVGA's authoritative answer key is the project's solutions guide and GitHub
(github.com/dolevf/Damn-Vulnerable-GraphQL-Application); the app also links a
"Solutions" page per challenge. Introspection (DG1) is the fastest way to
enumerate the exact mutation/field names in the pinned build. Keep this file
aligned with the version in `apps/dvga/app.yml`.
