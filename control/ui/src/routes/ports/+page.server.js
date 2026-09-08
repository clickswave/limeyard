import { get } from '$lib/limed.server.js';

export async function load() {
	const ports = await get('/api/ports', { ports: [], off_loopback: [] });
	const doctor = await get('/api/doctor', { ok: null, checks: [] });
	return { ports, doctor };
}
