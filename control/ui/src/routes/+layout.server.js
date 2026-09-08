import { get } from '$lib/limed.server.js';

export async function load() {
	const status = await get('/api/status');
	return { status, limedUp: status !== null };
}
