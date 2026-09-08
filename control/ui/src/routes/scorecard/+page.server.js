import { get } from '$lib/limed.server.js';

export async function load() {
	const data = await get('/api/scorecards', { scorecards: [] });
	const cards = data.scorecards ?? [];
	return { latest: cards[0] ?? null, previous: cards[1] ?? null, history: cards };
}
