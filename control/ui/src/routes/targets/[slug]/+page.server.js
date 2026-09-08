import { error } from '@sveltejs/kit';
import { get } from '$lib/limed.server.js';

export async function load({ params }) {
	const target = await get(`/api/targets/${params.slug}`);
	if (!target) throw error(404, `no target '${params.slug}'`);
	return { target };
}
