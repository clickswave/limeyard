import { get } from '$lib/limed.server.js';

export async function load() {
	const data = await get('/api/credits', { credits: [] });
	return { credits: data.credits ?? [] };
}
