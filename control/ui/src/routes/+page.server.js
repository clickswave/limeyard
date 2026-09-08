import { get } from '$lib/limed.server.js';

export async function load() {
	const data = await get('/api/targets', { targets: [], kinds: [] });
	return { targets: data.targets ?? [], kinds: data.kinds ?? [] };
}
