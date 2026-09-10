/** Presentation helpers. Safe in the browser: no server-only imports. */

/** Licence strings that mean "do not redistribute this". */
export function licenceRisk(licence) {
	if (!licence) return true;
	const l = String(licence).toLowerCase();
	return l === 'none declared' || l === 'unknown' || l === '?';
}

/** How a target's author line should read, packager included when they differ. */
export function byline(upstream) {
	if (!upstream?.author) return null;
	if (upstream.packager && upstream.packager !== upstream.author) {
		return `${upstream.author}, packaged by ${upstream.packager}`;
	}
	return upstream.author;
}

export function staleDays(verified) {
	if (!verified) return null;
	const d = Date.parse(String(verified).slice(0, 10));
	if (Number.isNaN(d)) return null;
	return Math.floor((Date.now() - d) / 86400000);
}

export const STALE_AFTER = 180;

/** "GET /path ?param (query)" for a truth.yml `where` block. */
export function where(w) {
	if (!w) return '';
	return [w.method, w.path, w.param ? `?${w.param}` : '', w.in ? `(${w.in})` : '']
		.filter(Boolean)
		.join(' ');
}

/** A target's address for a list: the URL without its scheme, or its lab IP. */
export function address(t) {
	if (t.url) return t.url.replace(/^https?:\/\//, '');
	if (t.lab_ips?.length) return t.lab_ips.length > 1 ? `${t.lab_ips[0]} +${t.lab_ips.length - 1}` : t.lab_ips[0];
	return '';
}

export function firstPort(t) {
	const p = (t.ports ?? []).map((x) => Number(x.port)).filter((n) => !Number.isNaN(n));
	return p.length ? Math.min(...p) : Infinity;
}

/** 0.8125 -> "0.813"; null -> "—" (the U+2014 stays out of prose, but a
 *  table cell with no number is exactly what it is for). */
export function ratio(v) {
	return v == null ? '—' : Number(v).toFixed(3);
}

export function delta(now, before) {
	if (now == null || before == null) return null;
	const d = now - before;
	if (Math.abs(d) < 0.0005) return null;
	return `${d > 0 ? '+' : '−'}${Math.abs(d).toFixed(3)}`;
}

/** ISO timestamp -> "2026-09-10 09:12" in the viewer's zone. */
export function when(iso) {
	if (!iso) return '';
	const d = new Date(iso);
	if (Number.isNaN(d.getTime())) return String(iso);
	const p = (n) => String(n).padStart(2, '0');
	return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** Digest display: "repo:tag" and "sha256:9c4e…a7f0". */
export function imageParts(ref) {
	const [name, digest] = String(ref).split('@');
	const short = digest ? `${digest.slice(0, 11)}…${digest.slice(-4)}` : null;
	return { name, digest, short };
}

export function clockNow() {
	const d = new Date();
	const p = (n) => String(n).padStart(2, '0');
	return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
