<script>
	import { invalidateAll } from '$app/navigation';
	import { onMount } from 'svelte';
	import { byline, licenceRisk } from '$lib/format.js';
	import MultiStart from '$lib/MultiStart.svelte';

	let { data } = $props();

	let q = $state('');
	let kind = $state('');
	let state_ = $state('');
	let sort = $state('kind');
	let dir = $state(1);
	let perPage = $state(25);
	let pageNo = $state(1);
	let busy = $state({});
	let selected = $state(new Set());
	let panel = $state(false);

	let kinds = $derived([...new Set(data.targets.map((t) => t.kind))].sort());
	let states = $derived([...new Set(data.targets.map((t) => t.state.split(' ')[0]))].sort());

	let filtered = $derived(
		data.targets.filter((t) => {
			if (kind && t.kind !== kind) return false;
			if (state_ && !t.state.startsWith(state_)) return false;
			if (!q) return true;
			return `${t.name} ${t.slug} ${t.description ?? ''} ${t.upstream.author ?? ''} ${t.stack ?? ''}`
				.toLowerCase()
				.includes(q.toLowerCase());
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
	let allOnPageSelected = $derived(rows.length > 0 && rows.every((t) => selected.has(t.slug)));

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

	function toggle(slug) {
		const next = new Set(selected);
		if (next.has(slug)) next.delete(slug);
		else next.add(slug);
		selected = next;
	}
	function togglePage() {
		const next = new Set(selected);
		if (allOnPageSelected) rows.forEach((t) => next.delete(t.slug));
		else rows.forEach((t) => next.add(t.slug));
		selected = next;
	}

	let timers = {};
	function release(slug) {
		clearTimeout(timers[slug]);
		delete timers[slug];
		busy = { ...busy, [slug]: null };
	}

	async function act(slug, action) {
		if (busy[slug]) return; // a second click while the first is in flight
		busy = { ...busy, [slug]: action };
		try {
			const r = await fetch(`/api/targets/${slug}/${action}`, { method: 'POST' });
			if (!r.ok) {
				const j = await r.json().catch(() => ({}));
				alert(j.error ?? `failed to ${action} ${slug}`);
				return release(slug);
			}
		} catch (e) {
			alert(String(e));
			return release(slug);
		}
		// Cleared by the SSE state event below. The timer is only a floor, so a
		// stuck image pull cannot lock the row forever.
		timers[slug] = setTimeout(() => {
			release(slug);
			invalidateAll();
		}, 45000);
	}

	onMount(() => {
		const es = new EventSource('/api/events');
		let t;
		es.addEventListener('state', (e) => {
			const { slug } = JSON.parse(e.data);
			if (busy[slug]) release(slug);
			clearTimeout(t);
			t = setTimeout(invalidateAll, 300);
		});
		return () => {
			clearTimeout(t);
			Object.values(timers).forEach(clearTimeout);
			es.close();
		};
	});

	const tone = (s) =>
		s === 'running' ? 'run' : s === 'unhealthy' ? 'stop' : s === 'stopped' ? 'idle' : 'wait';
	const caret = (c) => (sort === c ? (dir === 1 ? '↑' : '↓') : '');
</script>

<div class="head">
	<h1>Targets</h1>
	<span class="faint small">{data.targets.length}</span>
	<span class="spacer"></span>
	{#if selected.size}
		<span class="faint small">{selected.size} selected</span>
		<button class="btn sm" onclick={() => (selected = new Set())}>Clear</button>
	{/if}
	<button class="btn solid" onclick={() => (panel = true)}>Start targets</button>
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
			}}>Reset</button
		>
	{/if}
	<span class="spacer"></span>
	<select bind:value={perPage} title="rows per page">
		<option value={25}>25 rows</option>
		<option value={50}>50 rows</option>
		<option value={10}>10 rows</option>
	</select>
</div>

<div class="table-wrap">
	<table>
		<thead>
			<tr>
				<th class="pick">
					<input
						type="checkbox"
						checked={allOnPageSelected}
						onchange={togglePage}
						aria-label="Select page"
					/>
				</th>
				<th><button class="sortcol" onclick={() => setSort('name')}>Target {caret('name')}</button></th>
				<th><button class="sortcol" onclick={() => setSort('kind')}>Kind {caret('kind')}</button></th>
				<th><button class="sortcol" onclick={() => setSort('state')}>State {caret('state')}</button></th>
				<th>Endpoint</th>
				<th><button class="sortcol" onclick={() => setSort('author')}>Author {caret('author')}</button></th>
				<th>Key</th>
				<th class="right">Actions</th>
			</tr>
		</thead>
		<tbody>
			{#each rows as t (t.slug)}
				<tr class:pending={!!busy[t.slug]} class:selected={selected.has(t.slug)}>
					<td class="pick">
						<input
							type="checkbox"
							checked={selected.has(t.slug)}
							onchange={() => toggle(t.slug)}
							aria-label="Select {t.name}"
						/>
					</td>
					<td>
						<a class="tname" href="/targets/{t.slug}" title={t.description ?? ''}>{t.name}</a>
						{#if t.heavy}<span class="tag"> heavy</span>{/if}
					</td>
					<td class="muted small">{t.kind}</td>
					<td>
						<span class="status {tone(t.state.split(' ')[0])}"><i class="dot"></i>{t.state}</span>
					</td>
					<td class="mono">
						{#if t.url}
							<a class="endpoint" href={t.url} target="_blank" rel="noreferrer noopener" title={t.url}
								>{t.url.replace('http://', '')}</a
							>
						{:else}<span class="faint">lab network</span>{/if}
					</td>
					<!-- Attribution is a column, not a hover. Almost every target here is
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
							<span class="tag" class:alert={licenceRisk(t.upstream.license)}
								>{t.upstream.license}</span
							>
						{:else}<span class="tag alert">author missing</span>{/if}
					</td>
					<td class="faint small">{t.has_truth ? '✓' : '—'}</td>
					<td class="right nowrap">
						{#if t.kind === 'mobile'}
							<span class="faint small">fixture</span>
						{:else if t.state === 'stopped'}
							<button
								class="btn primary"
								disabled={!!busy[t.slug]}
								onclick={() => act(t.slug, 'start')}
							>
								{busy[t.slug] === 'start' ? 'Starting…' : 'Start'}
							</button>
						{:else}
							<button class="btn" disabled={!!busy[t.slug]} onclick={() => act(t.slug, 'restart')}
								>Restart</button
							>
							<button class="btn danger" disabled={!!busy[t.slug]} onclick={() => act(t.slug, 'stop')}>
								{busy[t.slug] === 'stop' ? 'Stopping…' : 'Stop'}
							</button>
						{/if}
					</td>
				</tr>
			{/each}
			{#if !rows.length}
				<tr><td colspan="8" class="empty">No targets match those filters.</td></tr>
			{/if}
		</tbody>
	</table>
</div>

<div class="pager">
	<span class="faint small">
		{#if sorted.length}
			{(clamped - 1) * perPage + 1}–{Math.min(clamped * perPage, sorted.length)} of {sorted.length}
		{:else}Nothing to show{/if}
	</span>
	<span class="spacer"></span>
	{#if pages > 1}
		<button class="btn sm" disabled={clamped <= 1} onclick={() => (pageNo = clamped - 1)}>Prev</button>
		<span class="faint small">{clamped} / {pages}</span>
		<button class="btn sm" disabled={clamped >= pages} onclick={() => (pageNo = clamped + 1)}>Next</button>
	{/if}
</div>

{#if panel}
	<MultiStart
		targets={data.targets}
		{selected}
		onclose={() => (panel = false)}
		onchanged={invalidateAll}
	/>
{/if}

<style>
	.head { display: flex; align-items: center; gap: 10px; margin-bottom: 18px; }
	.spacer { flex: 1; }
	.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 14px; flex-wrap: wrap; }
	.toolbar input[type='search'] { width: 280px; }
	.sortcol {
		background: none; border: 0; padding: 0; font: inherit; color: inherit;
		text-transform: inherit; letter-spacing: inherit; cursor: pointer;
	}
	.sortcol:hover { color: var(--ink-2); }
	.tname { font-weight: 500; }
	.author {
		font-size: 12.5px; color: var(--ink-2); max-width: 270px;
		overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
	}
	.endpoint {
		display: block; max-width: 285px; overflow: hidden;
		text-overflow: ellipsis; white-space: nowrap; color: var(--ink-2);
	}
	.endpoint:hover { color: var(--accent); }
	.pick { width: 1%; padding-right: 0; }
	.pager { display: flex; align-items: center; gap: 10px; margin-top: 14px; }

	/* Everything but Target is sized to content, so there is no dead gap. */
	th:nth-child(1), th:nth-child(3), th:nth-child(4),
	th:nth-child(7), th:nth-child(8) { width: 1%; white-space: nowrap; }
	th:nth-child(5) { width: 300px; }
	th:nth-child(6) { width: 290px; }
</style>
