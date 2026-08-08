# vulns

Per-app "answer keys" for the fleet: what each target is supposed to be
vulnerable to, so you can validate a scanner's findings against ground truth.

Every file follows the same structure:

1. Title + one-line intro (answer key, unlabelled in the app, for maintainers).
2. An **Intentionally vulnerable / isolated testing only** warning.
3. App facts: how to start it, base URL, and demo accounts.
4. A **status legend** (Live vs Seeded).
5. A **Summary** table: `ID | Vulnerability | Category | Status`.
6. One section per vuln with **Where**, **Reproduce**, **Real-world fix**.
7. **Notes and scope**.

## Catalogs

| App | File | Notes |
|-----|------|-------|
| faultline | [faultline.md](faultline.md) | our app; mirrors vulns.md in the faultline repo |
| crapi | [crapi.md](crapi.md) | OWASP crAPI; follows its built-in challenge set |

The upstream apps in the fleet already ship authoritative answer keys, so the
fastest ground truth for them is the source rather than a copy here:

- **juice-shop** - the in-app Score Board (`/#/score-board`) lists every challenge.
- **dvwa** - each module is self-labelled; behaviour changes with the security level.
- **webgoat** - each lesson states its own objective.
- **vampi** - see the VAmPI repo README (OWASP API Top 10 mapping).
- **dvga** - see the DVGA repo's solutions.
- **bwapp** - the bug dropdown enumerates every category.
- **log4shell** - single CVE: CVE-2021-44228 (Log4Shell), JNDI lookup in a logged field.

To add a local catalog for one of the above (or any new app), copy the shape of
`crapi.md` and keep the same headings.
