<script>
	import { invalidateAll } from '$app/navigation';
	import { onMount } from 'svelte';
	import { byline, licenceRisk } from '$lib/format.js';

	let { data } = $props();

	let q = $state('');
	let kind = $state('');
	let state_ = $state('');
	let sort = $state('kind');
	let dir = $state(1);
	let perPage = $state(25);
	let pageNo = $state(1);
	let busy = $state({});

	let kinds = $derived([...new Set(data.targets.map((t) => t.kind))].sort());
	let states = $derived([...new Set(data.targets.map((t) => t.state.split(' ')[0]))].sort());

	let filtered = $derived(
		data.targets.filter((t) => {
			if (kind && t.kind !== kind) return false;
			if (state_ && !t.state.startsWith(state_)) return false;
			if (q) {
				const hay = `${t.name} ${t.slug} ${t.description ?? ''} ${t.upstream.author ?? ''} ${
					t.stack ?? ''
				}`.toLowerCase();
				if (!hay.includes(q.toLowerCase())) return false;
			}
			return true;
		})
	);

	let sorted = $derived(
		[...filtered].sort((a, b) => {
			const key = (t) =>
				sort === 'name'
					? t.name.toLowerCase()
					: sort === 'state'
						? t.state
						: sort === 'author'
							? (t.upstream.author ?? '~').toLowerCase()
							: `${t.kind}~${t.name.toLowerCase()}`;
			return key(a) < key(b) ? -dir : key(a) > key(b) ? dir : 0;
		})
	);

	let pages = $derived(Math.max(1, Math.ceil(sorted.length / perPage)));
	let clamped = $derived(Math.min(pageNo, pages));
	let rows = $derived(sorted.slice((clamped - 1) * perPage, clamped * perPage));

	// Any filter change puts you back on page one, otherwise you land on an
	// empty page and think the filter matched nothing.
	$effect(() => {
		q;
		kind;
		state_;
		perPage;
		pageNo = 1;
	});

	function setSort(col) {
		if (sort === col) dir = -dir;
		else {
			sort = col;
			dir = 1;
		}
	}

	async function act(slug, action) {
		busy = { ...busy, [slug]: action };
		const r = await fetch(`/api/targets/${slug}/${action}`, { method: 'POST' });
		if (!r.ok) {
			const j = await r.json().catch(() => ({}));
			alert(j.error ?? `failed to ${action} ${slug}`);
		}
		setTimeout(() => {
			busy = { ...busy, [slug]: null };
			invalidateAll();
		}, 1500);
	}

	onMount(() => {
		const es = new EventSource('/api/events');
		let t;
		es.addEventListener('state', () => {
			clearTimeout(t);
			t = setTimeout(invalidateAll, 400);
		});
		return () => {
			clearTimeout(t);
			es.close();
		};
	});

	const tone = (s) =>
		s === 'running' ? 'ok' : s === 'unhealthy' ? 'crit' : s === 'stopped' ? '' : 'warn';
	const caret = (col) => (sort === col ? (dir === 1 ? ' ↑' : ' ↓') : '');
</script>

<div class="head">
	<h1>Targets</h1>
	<span class="faint small">{data.targets.length} across {kinds.length} kinds</span>
</div>

<div class="toolbar">
	<input type="search" placeholder="Search name, author, stack…" bind:value={q} />
	<select bind:value={kind}>
		<option value="">All kinds</option>
		{#each kinds as k}<option value={k}>{k}</option>{/each}
	</select>
	<select bind:value={state_}>
		<option value="">Any state</option>
		{#each states as s}<option value={s}>{s}</option>{/each}
	</select>
	{#if q || kind || state_}
		<button
			class="btn sm"
			onclick={() => {
				q = '';
				kind = '';
				state_ = '';
			}}>Clear</button
		>
	{/if}
	<span class="spacer"></span>
	<select bind:value={perPage} title="rows per page">
		<option value={10}>10</option>
		<option value={25}>25</option>
		<option value={50}>50</option>
	</select>
</div>

<div class="table-wrap">
	<table>
		<thead>
			<tr>
				<th><button class="sortcol" onclick={() => setSort('name')}>Target{caret('name')}</button></th
				>
				<th><button class="sortcol" onclick={() => setSort('kind')}>Kind{caret('kind')}</button></th>
				<th
					><button class="sortcol" onclick={() => setSort('state')}>State{caret('state')}</button></th
				>
				<th>Endpoint</th>
				<th
					><button class="sortcol" onclick={() => setSort('author')}>Author{caret('author')}</button
					></th
				>
				<th>Key</th>
				<th class="right">Actions</th>
			</tr>
		</thead>
		<tbody>
			{#each rows as t (t.slug)}
				<tr>
					<td>
						<a class="tname" href="/targets/{t.slug}">{t.name}</a>
						{#if t.heavy}<span class="badge">heavy</span>{/if}
						<div class="faint small desc">{t.description ?? ''}</div>
					</td>
					<td><span class="badge">{t.kind}</span></td>
					<td class="nowrap"
						><span class="badge {tone(t.state.split(' ')[0])}"><i class="dot"></i>{t.state}</span></td
					>
					<td class="mono">
						{#if t.url}<a class="endpoint" href={t.url} target="_blank" rel="noreferrer noopener" title={t.url}
								>{t.url}</a
							>
						{:else}<span class="faint endpoint">lab network</span>{/if}
					</td>
					<!-- Attribution is a column, not a hover. Nearly every target is
					     someone else's work and several declare no licence. -->
					<td>
						{#if t.upstream.author}
							<div class="author" title={byline(t.upstream)}>
								{#if t.upstream.repo}
									<a href={t.upstream.repo} target="_blank" rel="noreferrer noopener"
										>{byline(t.upstream)}</a
									>
								{:else}{byline(t.upstream)}{/if}
							</div>
							<span class="badge {licenceRisk(t.upstream.license) ? 'crit' : ''}"
								>{t.upstream.license}</span
							>
						{:else}
							<span class="badge crit">author missing</span>
						{/if}
					</td>
					<td>
						{#if t.has_truth}<span class="badge accent">yes</span>{:else}<span class="faint small"
								>none</span
							>{/if}
					</td>
					<td class="right nowrap">
						{#if t.kind === 'mobile'}
							<span class="faint small">fixture</span>
						{:else if t.state === 'stopped'}
							<button class="btn sm primary" disabled={!!busy[t.slug]} onclick={() => act(t.slug, 'start')}>
								{busy[t.slug] === 'start' ? 'Starting…' : 'Start'}
							</button>
						{:else}
							<button class="btn sm" disabled={!!busy[t.slug]} onclick={() => act(t.slug, 'restart')}
								>Restart</button
							>
							<button class="btn sm" disabled={!!busy[t.slug]} onclick={() => act(t.slug, 'stop')}>
								{busy[t.slug] === 'stop' ? 'Stopping…' : 'Stop'}
							</button>
						{/if}
					</td>
				</tr>
			{/each}
			{#if !rows.length}
				<tr><td colspan="7" class="empty">No targets match those filters.</td></tr>
			{/if}
		</tbody>
	</table>
</div>

<div class="pager">
	<span class="faint small">
		{#if sorted.length}
			{(clamped - 1) * perPage + 1}–{Math.min(clamped * perPage, sorted.length)} of {sorted.length}
		{:else}0 results{/if}
	</span>
	<span class="spacer"></span>
	<button class="btn sm" disabled={clamped <= 1} onclick={() => (pageNo = clamped - 1)}>Prev</button>
	<span class="small faint">Page {clamped} of {pages}</span>
	<button class="btn sm" disabled={clamped >= pages} onclick={() => (pageNo = clamped + 1)}
		>Next</button
	>
</div>

<style>
	.head {
		display: flex;
		align-items: baseline;
		gap: 10px;
		margin-bottom: 16px;
	}
	.toolbar {
		display: flex;
		gap: 8px;
		align-items: center;
		margin-bottom: 12px;
		flex-wrap: wrap;
	}
	.toolbar input[type='search'] {
		width: 260px;
	}
	.spacer {
		flex: 1;
	}
	.sortcol {
		background: none;
		border: 0;
		padding: 0;
		font: inherit;
		color: inherit;
		text-transform: inherit;
		letter-spacing: inherit;
		cursor: pointer;
	}
	.sortcol:hover {
		color: var(--ink);
	}
	.tname {
		font-weight: 500;
		color: var(--ink);
	}
	.tname:hover {
		color: var(--accent);
		text-decoration: none;
	}
	.desc {
		max-width: 300px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		margin-top: 1px;
	}
	.author {
		font-size: 12.5px;
		color: var(--ink-2);
		max-width: 200px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	td .badge {
		margin-top: 3px;
	}
	/* Fixed column widths keep every row one height, so the table scans.
	   Everything but Target and Endpoint is sized to its content. */
	th:nth-child(1) { width: 27%; }
	th:nth-child(2),
	th:nth-child(3),
	th:nth-child(6),
	th:nth-child(7) { width: 1%; white-space: nowrap; }
	th:nth-child(5) { width: 190px; }
	.endpoint {
		display: block;
		max-width: 230px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.pager {
		display: flex;
		align-items: center;
		gap: 10px;
		margin-top: 12px;
	}
</style>
