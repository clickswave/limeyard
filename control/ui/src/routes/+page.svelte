<script>
	import { goto } from '$app/navigation';
	import { live, shownState, isBusy } from '$lib/live.svelte.js';
	import { actTarget, actMany } from '$lib/actions.js';
	import { address, firstPort } from '$lib/format.js';
	import State from '$lib/State.svelte';

	let { data } = $props();

	let query = $state('');
	let kind = $state('all');
	let st = $state('all');
	let sort = $state('name');
	let selected = $state(new Set());
	let problem = $state('');

	const ORDER = { running: 0, starting: 1, stopping: 1, pulling: 1, setup: 1, partial: 2, unhealthy: 3, stopped: 4, missing: 5, fixture: 6 };

	/** What a row shows. Fixtures have nothing to run and say so. */
	const stateOf = (t) => (t.fixture ? 'fixture' : shownState(t.slug, t.state).split(' ')[0]);

	let kinds = $derived([...new Set(data.targets.map((t) => t.kind))].sort());
	let states = $derived([...new Set(data.targets.map(stateOf))].sort((a, b) => (ORDER[a] ?? 9) - (ORDER[b] ?? 9)));

	let rows = $derived.by(() => {
		const q = query.trim().toLowerCase();
		const list = data.targets.filter((t) => {
			if (kind !== 'all' && t.kind !== kind) return false;
			if (st !== 'all' && stateOf(t) !== st) return false;
			if (!q) return true;
			return `${t.name} ${t.slug} ${t.stack ?? ''} ${t.upstream.author ?? ''} ${t.description ?? ''}`
				.toLowerCase()
				.includes(q);
		});
		const by = {
			name: (a, b) => a.name.localeCompare(b.name),
			kind: (a, b) => a.kind.localeCompare(b.kind) || a.name.localeCompare(b.name),
			port: (a, b) => firstPort(a) - firstPort(b) || a.name.localeCompare(b.name),
			state: (a, b) => (ORDER[stateOf(a)] ?? 9) - (ORDER[stateOf(b)] ?? 9) || a.name.localeCompare(b.name)
		}[sort];
		return list.slice().sort(by);
	});

	let counts = $derived.by(() => {
		const c = {};
		for (const t of data.targets) c[stateOf(t)] = (c[stateOf(t)] ?? 0) + 1;
		return c;
	});
	let countsLine = $derived(
		`${counts.running ?? 0} running · ${counts.stopped ?? 0} stopped · ${counts.unhealthy ?? 0} unhealthy · ${data.targets.length} total`
	);

	let filtersDirty = $derived(!!query || kind !== 'all' || st !== 'all' || sort !== 'name');
	let picked = $derived(data.targets.filter((t) => selected.has(t.slug)));
	let heavyPicked = $derived(picked.filter((t) => t.heavy).length);
	let allChecked = $derived(rows.length > 0 && rows.every((t) => selected.has(t.slug)));

	function clearFilters() {
		query = '';
		kind = 'all';
		st = 'all';
		sort = 'name';
	}
	function toggle(slug) {
		const next = new Set(selected);
		next.has(slug) ? next.delete(slug) : next.add(slug);
		selected = next;
	}
	function toggleAll() {
		const next = new Set(selected);
		if (allChecked) rows.forEach((t) => next.delete(t.slug));
		else rows.forEach((t) => !t.fixture && next.add(t.slug));
		selected = next;
	}

	const live_ = (t) => ['running', 'starting', 'partial', 'unhealthy'].includes(stateOf(t));

	async function one(t, action) {
		problem = '';
		const err = await actTarget(t.slug, action);
		if (err) problem = `${t.name}: ${err}`;
	}
	async function bulk(action) {
		problem = '';
		const slugs = picked.filter((t) => !t.fixture).map((t) => t.slug);
		const { error, refused } = await actMany(slugs, action);
		if (error) problem = error;
		else if (refused.length) problem = refused.map((r) => `${r.slug}: ${r.error}`).join(' · ');
		selected = new Set();
	}
	const open = (t) => goto(`/targets/${t.slug}`);
	const stop = (e) => e.stopPropagation();
</script>

<svelte:head><title>Targets · limeyard</title></svelte:head>

<main class="page">
	<div class="head">
		<h1>Targets</h1>
		<div class="small muted num">{countsLine}</div>
	</div>

	<div class="toolbar">
		<input class="inp" type="search" placeholder="Search name, slug, stack" bind:value={query} style="width:250px;max-width:100%" />
		<select class="sel" bind:value={kind} aria-label="Filter by kind">
			<option value="all">All kinds</option>
			{#each kinds as k}<option value={k}>{k}</option>{/each}
		</select>
		<select class="sel" bind:value={st} aria-label="Filter by state">
			<option value="all">Any state</option>
			{#each states as s}<option value={s}>{s}</option>{/each}
		</select>
		<select class="sel" bind:value={sort} aria-label="Sort order">
			<option value="name">Sort by name</option>
			<option value="state">Sort by state</option>
			<option value="kind">Sort by kind</option>
			<option value="port">Sort by port</option>
		</select>
		{#if filtersDirty}<button class="btn" onclick={clearFilters}>Clear</button>{/if}
	</div>

	<!-- A fixed-height strip: ticking a row never shifts the table. -->
	<div class="strip">
		{#if picked.length}
			<span class="small num" style="font-weight:500">
				{picked.length} {picked.length === 1 ? 'target' : 'targets'} selected{heavyPicked ? ` · ${heavyPicked} heavy` : ''}
			</span>
			<span class="vr"></span>
			<button class="btn" onclick={() => bulk('start')}>Start</button>
			<button class="btn" onclick={() => bulk('stop')}>Stop</button>
			<button class="btn" onclick={() => bulk('restart')}>Restart</button>
			<button class="btn link" style="margin-left:auto" onclick={() => (selected = new Set())}>Clear selection</button>
		{:else}
			<span class="small muted">Select rows to start, stop or restart them together.</span>
		{/if}
	</div>
	{#if problem}<p class="tiny bad" style="margin-top:8px">{problem}</p>{/if}

	<div class="wrap" style="margin-top:14px">
		<table style="min-width:980px">
			<thead>
				<tr>
					<th style="width:34px"><input type="checkbox" checked={allChecked} onchange={toggleAll} aria-label="Select all" /></th>
					<th>Target</th>
					<th style="width:92px">Kind</th>
					<th style="width:124px">State</th>
					<th style="width:160px">Address</th>
					<th style="width:160px">Upstream</th>
					<th style="width:74px">Weight</th>
					<th class="r" style="width:150px">Actions</th>
				</tr>
			</thead>
			<tbody>
				{#each rows as t (t.slug)}
					{@const s = stateOf(t)}
					{@const busy = isBusy(t.slug)}
					<tr class="click" class:pending={busy} onclick={() => open(t)} style="height:46px">
						<td onclick={stop}>
							{#if !t.fixture}
								<input type="checkbox" checked={selected.has(t.slug)} onchange={() => toggle(t.slug)} aria-label={t.name} />
							{/if}
						</td>
						<td>
							<div style="font-weight:500;line-height:1.3">{t.name}</div>
							<div class="mono muted" style="font-size:11.5px;line-height:1.4">{t.slug}</div>
						</td>
						<td class="mono muted tiny">{t.kind}</td>
						<td><State state={s} /></td>
						<td class="mono muted tiny">{address(t) || (t.fixture ? 'APK fixture' : '')}</td>
						<td class="muted small" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:160px" title={t.upstream.author ?? ''}>
							{t.upstream.author ?? 'author missing'}
						</td>
						<td class="muted small">{t.heavy ? 'heavy' : '—'}</td>
						<td class="r" onclick={stop} style="white-space:nowrap">
							{#if t.fixture}
								<span class="muted small">nothing to run</span>
							{:else}
								<button class="btn sm" disabled={busy} onclick={() => one(t, live_(t) ? 'stop' : 'start')}>
									{live_(t) ? 'Stop' : 'Start'}
								</button>
								<button class="btn sm" disabled={busy} onclick={() => one(t, 'restart')} style="margin-left:6px">Restart</button>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	{#if !rows.length}
		<div class="empty">
			<div class="t">No targets match those filters.</div>
			<div class="s">{data.targets.length ? 'Nothing in the lab matches this combination right now.' : 'The daemon reported no targets. Is LIMEYARD_DIR pointing at the checkout?'}</div>
			{#if filtersDirty}<button class="btn" onclick={clearFilters} style="margin-top:16px">Clear filters</button>{/if}
		</div>
	{/if}
</main>

<style>
	.strip {
		height: 40px;
		display: flex;
		align-items: center;
		gap: 10px;
		margin-top: 16px;
		border-bottom: 1px solid var(--line);
	}
	.vr { width: 1px; height: 16px; background: var(--line-ctl); }
</style>
