/** Lifecycle calls. Every one returns an error string or null so the caller
 *  can put the reason where the click happened instead of in an alert. */
import { markPending, release } from '$lib/live.svelte.js';

async function post(path, body) {
	try {
		const r = await fetch(path, {
			method: 'POST',
			headers: body ? { 'Content-Type': 'application/json' } : {},
			body: body ? JSON.stringify(body) : undefined
		});
		const j = await r.json().catch(() => ({}));
		if (!r.ok) return { error: j.error ?? `HTTP ${r.status}`, data: j };
		return { error: null, data: j };
	} catch (e) {
		return { error: e.message, data: null };
	}
}

export async function actTarget(slug, action) {
	markPending(slug, action);
	const { error } = await post(`/api/targets/${slug}/${action}`);
	if (error) release(slug);
	return error;
}

/** Returns { refused: [{slug, error}] } or an error string. */
export async function actMany(slugs, action) {
	slugs.forEach((s) => markPending(s, action));
	const { error, data } = await post('/api/targets/bulk', { action, slugs });
	if (error) {
		slugs.forEach(release);
		return { error, refused: [] };
	}
	for (const r of data.refused ?? []) release(r.slug);
	return { error: null, refused: data.refused ?? [] };
}

export async function actScenario(slug, action) {
	markPending(`scenario:${slug}`, action, 90000);
	const { error } = await post(`/api/scenarios/${slug}/${action}`);
	if (error) release(`scenario:${slug}`);
	return error;
}

export async function runFix(ids) {
	return post('/api/doctor/fix', { ids });
}
