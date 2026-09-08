import { LIMED } from '$lib/limed.server.js';

/** Thin proxy so the browser never needs to reach limed directly, and so SSE
 *  streams (logs, events) pass through unbuffered. */
async function pipe(event, method) {
	const { path } = event.params;
	const qs = event.url.search || '';
	const init = { method, headers: {}, signal: event.request.signal };
	if (method === 'POST') {
		init.headers['Content-Type'] = 'application/json';
		init.body = await event.request.text();
	}
	let r;
	try {
		r = await fetch(`${LIMED}/api/${path}${qs}`, init);
	} catch (e) {
		return new Response(JSON.stringify({ error: `limed unreachable: ${e.message}` }), {
			status: 502,
			headers: { 'Content-Type': 'application/json' }
		});
	}
	const ct = r.headers.get('content-type') || 'application/json';
	if (ct.includes('text/event-stream')) {
		return new Response(r.body, {
			headers: {
				'Content-Type': 'text/event-stream',
				'Cache-Control': 'no-cache',
				Connection: 'keep-alive'
			}
		});
	}
	return new Response(await r.text(), { status: r.status, headers: { 'Content-Type': ct } });
}

export const GET = (event) => pipe(event, 'GET');
export const POST = (event) => pipe(event, 'POST');
