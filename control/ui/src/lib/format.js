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
