import { get } from '$lib/limed.server.js';

export async function load() {
	const doctor = await get('/api/doctor', null);
	return { doctor };
}
