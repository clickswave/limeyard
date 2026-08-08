# vulns

Per-app "answer keys" for the fleet: what each target is supposed to be
vulnerable to, so you can validate a scanner's findings against ground truth.
There is one file per app, all in the same shape.

Every file follows the same structure:

1. Title + one-line intro (answer key, unlabelled in the app, for maintainers).
2. An **Intentionally vulnerable / isolated testing only** warning.
3. App facts: how to start it, base URL, and demo accounts.
4. A **status legend** (Live vs Seeded).
5. A **Summary** table: `ID | Vulnerability | Category | Status`.
6. One section per vuln with **Where**, **Reproduce**, **Real-world fix**.
7. **Notes and scope** (points to the app's own authoritative key).

## Catalogs

| App | File | Focus |
|-----|------|-------|
| juice-shop | [juice-shop.md](juice-shop.md) | modern SPA + REST; broad OWASP Top 10 |
| dvwa | [dvwa.md](dvwa.md) | classic modules, adjustable security level |
| webgoat | [webgoat.md](webgoat.md) | Java lessons + WebWolf out-of-band |
| vampi | [vampi.md](vampi.md) | OWASP API Top 10 |
| dvga | [dvga.md](dvga.md) | GraphQL (introspection, injection, DoS) |
| bwapp | [bwapp.md](bwapp.md) | 100+ bugs across every class |
| log4shell | [log4shell.md](log4shell.md) | CVE-2021-44228 (JNDI RCE) |
| crapi | [crapi.md](crapi.md) | OWASP crAPI challenge set |
| faultline | [faultline.md](faultline.md) | our app; mirrors the faultline repo's vulns.md |

Each file's **Notes and scope** section links to that app's own authoritative
answer key (the in-app Score Board, module View Source, lesson objectives, the
bug dropdown, the CVE advisory, etc.), which stays the source of truth.

To add a catalog for a new app, copy the shape of any file here and keep the
same headings.
