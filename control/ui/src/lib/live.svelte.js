/** One EventSource for the whole panel. limed ticks every few seconds with the
 *  full state map, so a page that mounts late is current after one event, and
 *  emits a `state` event on every transition, which is when we reload data.
 *
 *  `pending` is the optimistic layer: the moment a button is pressed the row
 *  shows "starting" or "stopping" until limed reports the transition, or a
 *  floor timer gives up so a stuck pull cannot freeze a row forever. */
import { invalidateAll } from '$app/navigation';

export const live = $state({
	connected: false,
	states: {},
	scenarios: {},
	pending: {},
	tick: 0,
	host: null,
	disk: null
});

const PENDING_LABEL = {
	start: 'starting',
	restart: 'starting',
	stop: 'stopping',
	pull: 'pulling',
	setup: 'setup',
	up: 'starting',
	down: 'stopping'
};

let es = null;
let reload;
const floors = {};

export function connect() {
	if (es || typeof EventSource === 'undefined') return () => {};
	es = new EventSource('/api/events');
	es.onopen = () => (live.connected = true);
	es.onerror = () => (live.connected = false);
	es.addEventListener('tick', (e) => {
		const d = JSON.parse(e.data);
		live.states = d.states ?? {};
		live.scenarios = d.scenarios ?? {};
		live.tick = d.time;
		if (d.host) live.host = d.host;
		if (d.disk) live.disk = d.disk;
		live.connected = true;
	});
	const bump = (e) => {
		const { slug } = JSON.parse(e.data);
		release(slug);
		clearTimeout(reload);
		reload = setTimeout(() => invalidateAll(), 250);
	};
	es.addEventListener('state', bump);
	es.addEventListener('scenario', bump);
	return () => {
		es?.close();
		es = null;
		clearTimeout(reload);
	};
}

export function markPending(slug, action, floorMs = 45000) {
	live.pending[slug] = action;
	clearTimeout(floors[slug]);
	floors[slug] = setTimeout(() => {
		release(slug);
		invalidateAll();
	}, floorMs);
}

export function release(slug) {
	clearTimeout(floors[slug]);
	delete floors[slug];
	if (slug in live.pending) delete live.pending[slug];
}

/** The state a row should show right now: optimistic, then live, then loaded. */
export function shownState(slug, loaded) {
	const p = live.pending[slug];
	if (p) return PENDING_LABEL[p] ?? p;
	return live.states[slug] ?? loaded;
}

export function shownScenarioState(slug, loaded) {
	const p = live.pending[`scenario:${slug}`];
	if (p) return PENDING_LABEL[p] ?? p;
	return live.scenarios[slug] ?? loaded;
}

export function isBusy(slug) {
	return !!live.pending[slug];
}
