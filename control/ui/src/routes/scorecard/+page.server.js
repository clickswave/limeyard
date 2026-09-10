import { get } from '$lib/limed.server.js';

export async function load() {
	const data = await get('/api/scorecards', { scorecards: [] });
	return { history: data.scorecards ?? [] };
}
