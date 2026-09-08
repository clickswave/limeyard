import { get } from '$lib/limed.server.js';

export async function load() {
	const data = await get('/api/scenarios', { scenarios: [] });
	return { scenarios: data.scenarios ?? [] };
}
