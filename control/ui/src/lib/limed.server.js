import { env } from '$env/dynamic/private';

export const LIMED = env.LIMED_URL || 'http://127.0.0.1:7099';

/** GET from limed. Returns `fallback` on failure rather than exploding the page:
 *  a control panel that goes blank when the daemon blinks is worse than one that
 *  says the daemon blinked. */
export async function get(path, fallback = null) {
	try {
		const r = await fetch(`${LIMED}${path}`, { signal: AbortSignal.timeout(8000) });
		if (!r.ok) return fallback;
		return await r.json();
	} catch {
		return fallback;
	}
}
