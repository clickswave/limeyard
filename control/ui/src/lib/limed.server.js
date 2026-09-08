import { env } from '$env/dynamic/private';

export const LIMED = env.LIMED_URL || 'http://127.0.0.1:7099';

/** The shared secret limed requires. It lives only here, server side: the
 *  browser never sees it, so a viewer of this page cannot replay it. */
export const TOKEN = env.LIME_TOKEN || '';

export function authHeaders(extra = {}) {
	return TOKEN ? { ...extra, 'X-Lime-Token': TOKEN } : extra;
}

/** GET from limed. Returns `fallback` on failure rather than exploding the page:
 *  a control panel that goes blank when the daemon blinks is worse than one that
 *  says the daemon blinked. */
export async function get(path, fallback = null) {
	try {
		const r = await fetch(`${LIMED}${path}`, {
			headers: authHeaders(),
			signal: AbortSignal.timeout(8000)
		});
		if (!r.ok) return fallback;
		return await r.json();
	} catch {
		return fallback;
	}
}
