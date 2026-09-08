#!/usr/bin/env python3
"""mirage - a target where every finding is a false positive.

Nothing here is vulnerable. Every response is engineered to look like it might
be, so that a scanner which matches on appearance rather than on proof reports
something. That is the whole point: a lab full of genuinely vulnerable apps can
only measure recall, and a recall-only score is how a scanner ends up shipping
noisy heuristics.

Rules for anyone extending this:
  1. Never actually execute, interpolate, resolve, or include anything.
  2. Reflect input only after HTML-escaping it.
  3. Make the bait convincing. A trap nothing falls for measures nothing.

Stdlib only, no dependencies, so the image stays tiny and cannot rot.
"""
import html
import json
import random
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT = 8080

# Convincing, entirely fictional. These are the strings error-based SQLi oracles
# look for; none of them comes from a database, because there is no database.
SQL_ERRORS = [
    "You have an error in your SQL syntax; check the manual that corresponds to "
    "your MySQL server version for the right syntax to use near ''' at line 1",
    "Warning: pg_query(): Query failed: ERROR:  unterminated quoted string at or near \"'\"",
    "Microsoft OLE DB Provider for SQL Server error '80040e14' Unclosed quotation "
    "mark after the character string ''.",
    "ORA-01756: quoted string not properly terminated",
    "SQLite3::query(): near \"'\": syntax error",
]

# Looks like a stack trace with a file path. Discloses nothing real.
TRACE = ("Traceback (most recent call last):\n"
         '  File "/srv/app/views.py", line 142, in render\n'
         "    return template.render(**ctx)\n"
         "TemplateSyntaxError: unexpected '}'")


def page(title, body):
    return (f"<!doctype html><html><head><title>{title}</title></head><body>"
            f"<h1>{title}</h1>{body}"
            "<hr><p><small>mirage: nothing here is vulnerable. Every finding "
            "reported against this target is a false positive.</small></p>"
            "</body></html>").encode()


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "nginx"          # bait: a plausible, wrong server banner
    sys_version = ""

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        p = u.path.rstrip("/") or "/"
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        return self.route(p, q)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8", "replace") if n else ""
        q = {k: v[0] for k, v in parse_qs(raw).items()}
        return self.route(urlparse(self.path).path.rstrip("/") or "/", q)

    # ------------------------------------------------------------- routes ---
    def route(self, p, q):
        # ---- SOFT 404. Every unknown path answers 200 with a page that looks
        # real. Content discovery that does not calibrate reports the entire
        # wordlist as found.
        known = {"/", "/search", "/echo", "/profile", "/render", "/fetch",
                 "/download", "/redirect", "/ping", "/xml", "/login", "/admin",
                 "/api/config", "/.env", "/status", "/jsonp", "/slow"}
        if p not in known:
            return self._send(200, page(
                "Page not found",
                f"<p>No page at <code>{html.escape(p)}</code>. "
                "Try the <a href='/'>home page</a>.</p>"))

        if p == "/":
            links = "".join(f"<li><a href='{k}'>{k}</a></li>" for k in sorted(known - {"/"}))
            return self._send(200, page("mirage", f"<ul>{links}</ul>"))

        # ---- FAKE SQL ERRORS. Any quote-ish input produces a database error
        # that no database produced. Proof requires a behavioural difference,
        # and there is none: the same error appears for every input.
        if p == "/search":
            term = q.get("q", "")
            if re.search(r"['\"\\;]|--|\bor\b|\bunion\b", term, re.I):
                return self._send(200, page(
                    "Search error",
                    f"<pre>{html.escape(random.choice(SQL_ERRORS))}</pre>"))
            return self._send(200, page("Search", f"<p>No results for "
                                                  f"{html.escape(term)}.</p>"))

        # ---- SAFE REFLECTION. The payload comes back, correctly escaped, in
        # several contexts. It never executes. This is the single most common
        # source of XSS false positives.
        if p == "/echo":
            v = q.get("v", "")
            e = html.escape(v)
            return self._send(200, page("Echo", f"""
                <p>body: {e}</p>
                <div title="{html.escape(v, quote=True)}">attribute</div>
                <textarea>{e}</textarea>
                <script>var t = {json.dumps(v)};</script>"""))

        # ---- Reflection into what looks like a template, with a template-ish
        # error. `{{7*7}}` comes back as `{{7*7}}`, never 49.
        if p == "/render":
            t = q.get("tpl", "")
            if "{{" in t or "${" in t or "<%" in t:
                return self._send(500, page("Template error", f"<pre>{TRACE}</pre>"
                                                              f"<p>{html.escape(t)}</p>"))
            return self._send(200, page("Render", f"<p>{html.escape(t)}</p>"))

        # ---- SSRF bait. Accepts a url, never fetches it, echoes a plausible
        # "connection" line. An oracle that requires an actual callback is
        # unaffected; one that matches on wording is not.
        if p == "/fetch":
            url = q.get("url", "")
            return self._send(200, page("Fetch", (
                f"<pre>connecting to {html.escape(url)} ...\n"
                "connection refused after 3 attempts</pre>")))

        # ---- Traversal bait. Path-looking input is echoed inside a plausible
        # error. No file is ever opened.
        if p == "/download":
            f = q.get("file", "")
            return self._send(404, page("Not found", (
                f"<pre>fopen('/srv/data/{html.escape(f)}'): "
                "No such file or directory</pre>")))

        # ---- Open-redirect bait that does not redirect. 200, with the target
        # in the body and in a header that is not Location.
        if p == "/redirect":
            to = q.get("to", "/")
            return self._send(200, page("Redirect", f"<p>Would send you to "
                                                    f"{html.escape(to)}.</p>"),
                              extra={"X-Redirect-Target": to[:200]})

        # ---- Command-injection bait. Echoes a plausible ping transcript. The
        # shell arithmetic marker is never evaluated, so a reflected-cmdi oracle
        # that checks for the computed product stays silent, while one that
        # matches on "PING ... bytes of data" does not.
        if p == "/ping":
            host = q.get("host", "localhost")
            return self._send(200, page("Ping", (
                f"<pre>PING {html.escape(host)} 56(84) bytes of data.\n"
                "--- ping statistics ---\n"
                "3 packets transmitted, 0 received, 100% packet loss</pre>")))

        # ---- XXE bait. Accepts XML, never parses entities, echoes the doc.
        if p == "/xml":
            return self._send(200, page("XML", "<p>Document accepted. "
                                               "Entity expansion is disabled.</p>"))

        # ---- Login that is not bypassable. Always fails, and emits a SQL-ish
        # error on quote input while doing so.
        if p == "/login":
            u_ = q.get("username", "")
            if "'" in u_ or '"' in u_:
                return self._send(200, page("Login failed",
                                            f"<pre>{SQL_ERRORS[0]}</pre>"))
            return self._send(401, page("Login failed", "<p>Invalid credentials.</p>"))

        # ---- A public-by-design admin page. It is meant to be reachable, and
        # holds nothing. Reporting it as an exposed panel is a false positive.
        if p == "/admin":
            return self._send(200, page("Admin", (
                "<p>This page is public on purpose and contains nothing. "
                "It exists so that finding it is not a finding.</p>")))

        # ---- Config-shaped responses with obviously fictional values, to bait
        # secret scanners. No real key format validates.
        if p == "/api/config":
            return self._send(200, json.dumps({
                "env": "production",
                "api_key": "not-a-real-key-000000000000000000",
                "database_url": "postgres://user:pass@localhost/none",
                "debug": False,
            }), ctype="application/json")

        if p == "/.env":
            return self._send(404, page("Not found", "<p>No such file.</p>"))

        # ---- JSONP-shaped endpoint that escapes its callback.
        if p == "/jsonp":
            cb = re.sub(r"[^A-Za-z0-9_]", "", q.get("callback", "cb"))[:40]
            return self._send(200, f'{cb}({{"ok":true}})',
                              ctype="application/javascript")

        # ---- Uniformly slow, so time-based blind oracles see a delay that has
        # nothing to do with their payload. The delay is the same either way.
        if p == "/slow":
            time.sleep(2.0)
            return self._send(200, page("Slow", "<p>This endpoint always takes "
                                                "two seconds, for every input.</p>"))

        if p == "/status":
            return self._send(200, json.dumps({"ok": True}),
                              ctype="application/json")

        if p == "/profile":
            return self._send(200, page("Profile", "<p>Not logged in.</p>"))

        return self._send(404, page("Not found", ""))


if __name__ == "__main__":
    print(f"mirage on :{PORT} - everything here is a false positive")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
