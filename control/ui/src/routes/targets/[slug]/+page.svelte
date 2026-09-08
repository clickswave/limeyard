<script>
	import { invalidateAll } from '$app/navigation';
	import { onMount } from 'svelte';
	import { byline, licenceRisk, staleDays } from '$lib/format.js';

	let { data } = $props();
	let t = $derived(data.target);
	let logs = $state([]);
	let tailing = $state(false);
	let busy = $state(null);
	let showOos = $state(false);
	let es;

	let stale = $derived(staleDays(t.upstream?.verified));
	let expected = $derived(t.truth?.expected ?? []);
	let inScope = $derived(expected.filter((e) => (e.scope ?? 'black-box') !== 'out-of-scope'));
	let outOfScope = $derived(expected.filter((e) => e.scope === 'out-of-scope'));
	let negative = $derived(t.truth?.negative ?? []);
	let shown = $derived(showOos ? [...inScope, ...outOfScope] : inScope);

	async function act(action) {
		busy = action;
		await fetch(`/api/targets/${t.slug}/${action}`, { method: 'POST' });
		setTimeout(() => {
			busy = null;
			invalidateAll();
		}, 1500);
	}

	function toggleTail() {
		if (tailing) {
			es?.close();
			tailing = false;
			return;
		}
		logs = [];
		es = new EventSource(`/api/targets/${t.slug}/logs`);
		es.addEventListener('log', (e) => {
			logs = [...logs.slice(-400), JSON.parse(e.data).line];
		});
		tailing = true;
	}
	onMount(() => () => es?.close());

	const where = (w) =>
		!w
			? ''
			: [w.method, w.path, w.param ? `?${w.param}` : '', w.in ? `(${w.in})` : '']
					.filter(Boolean)
					.join(' ');
	const tone = (s) =>
		s === 'running' ? 'ok' : s === 'unhealthy' ? 'crit' : s === 'stopped' ? '' : 'warn';
</script>

<a class="back faint small" href="/">← Targets</a>

<div class="head">
	<h1>{t.name}</h1>
	<span class="badge">{t.kind}</span>
	<span class="badge {tone(t.state.split(' ')[0])}"><i class="dot"></i>{t.state}</span>
	<span class="spacer"></span>
	{#if t.kind !== 'mobile'}
		{#if t.state === 'stopped'}
			<button class="btn primary" disabled={!!busy} onclick={() => act('start')}
				>{busy === 'start' ? 'Starting…' : 'Start'}</button
			>
		{:else}
			<button class="btn" disabled={!!busy} onclick={() => act('restart')}>Restart</button>
			<button class="btn" disabled={!!busy} onclick={() => act('stop')}>Stop</button>
		{/if}
	{/if}
</div>

{#if t.description}<p class="lede muted">{t.description}</p>{/if}

<!-- Attribution first, above the vulnerability list. Whose work this is
     comes before what it is worth to us. -->
<section class="credit">
	<div class="ct">
		<span class="ck">Author</span>
		<span>
			{#if byline(t.upstream)}
				{#if t.upstream.repo}
					<a href={t.upstream.repo} target="_blank" rel="noreferrer noopener"
						>{byline(t.upstream)}</a
					>
				{:else}{byline(t.upstream)}{/if}
			{:else}<span class="badge crit">missing from target.yml</span>{/if}
		</span>
	</div>
	<div class="ct">
		<span class="ck">Licence</span>
		<span>
			<span class="badge {licenceRisk(t.upstream?.license) ? 'crit' : ''}"
				>{t.upstream?.license}</span
			>
			{#if licenceRisk(t.upstream?.license)}
				<span class="faint small">run internally only, never redistribute</span>
			{/if}
		</span>
	</div>
	{#if t.upstream?.homepage}
		<div class="ct">
			<span class="ck">Homepage</span>
			<a href={t.upstream.homepage} target="_blank" rel="noreferrer noopener"
				>{t.upstream.homepage}</a
			>
		</div>
	{/if}
	{#if t.upstream?.verified}
		<div class="ct">
			<span class="ck">Verified</span>
			<span
				>{t.upstream.verified}
				{#if stale != null}<span class="faint small"
						>{stale === 0 ? 'today' : stale === 1 ? 'yesterday' : `${stale} days ago`}{stale > 180
							? ', worth re-checking it still builds'
							: ''}</span
					>{/if}</span
			>
		</div>
	{/if}
	{#if t.upstream?.note}
		<div class="ct"><span class="ck">Note</span><span class="muted small">{t.upstream.note}</span></div>
	{/if}
</section>

<div class="facts">
	{#if t.url}<a class="badge accent" href={t.url} target="_blank" rel="noreferrer noopener"
			>{t.url}</a
		>{/if}
	{#if t.stack}<span class="badge">{t.stack}</span>{/if}
	{#if t.heavy}<span class="badge warn">heavy</span>{/if}
	{#if t.egress}<span class="badge">needs egress</span>{/if}
	{#if t.disk}<span class="badge">{t.disk}</span>{/if}
</div>

{#if t.setup}<p class="notice">{t.setup}</p>{/if}

{#if t.credentials?.length}
	<h2>Seeded credentials</h2>
	<div class="table-wrap">
		<table>
			<thead><tr><th>User</th><th>Password</th><th>Role</th></tr></thead>
			<tbody>
				{#each t.credentials as c}
					<tr
						><td class="mono">{c.user}</td><td class="mono">{c.pass}</td><td class="faint"
							>{c.role ?? '—'}</td
						></tr
					>
				{/each}
			</tbody>
		</table>
	</div>
{/if}

<h2>
	Answer key
	<span class="faint small" style="font-weight:400">ours, not upstream's</span>
</h2>
{#if !t.has_truth}
	<p class="notice">No <code>truth.yml</code>. This target cannot be scored.</p>
{:else}
	{#if t.truth?.note}<p class="notice">{t.truth.note}</p>{/if}
	<div class="keybar">
		<span class="faint small">
			{inScope.length} scored · {outOfScope.length} out of scope · {negative.length} negative controls
		</span>
		<span class="spacer"></span>
		{#if outOfScope.length}
			<label class="check"
				><input type="checkbox" bind:checked={showOos} /> Show out of scope</label
			>
		{/if}
	</div>
	{#if !shown.length}
		<p class="notice">
			Nothing scored here. {outOfScope.length
				? 'Every entry is out of scope; tick the box above to see them.'
				: 'This target is scored entirely on its negative controls below.'}
		</p>
	{:else}
	<div class="table-wrap">
		<table>
			<thead>
				<tr><th>ID</th><th>Class</th><th>Where</th><th>Scope</th><th>Confirmed by</th></tr>
			</thead>
			<tbody>
				{#each shown as e}
					<tr class:dimmed={e.scope === 'out-of-scope'}>
						<td class="mono">{e.id}</td>
						<td><span class="badge">{e.class}</span></td>
						<td class="mono">{where(e.where)}</td>
						<td
							><span class="badge {e.scope === 'authed' ? 'warn' : ''}"
								>{e.scope ?? 'black-box'}</span
							></td
						>
						<td class="faint small">{e.confirm ?? e.note ?? ''}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
	{/if}

	{#if negative.length}
		<h3>Negative controls — reporting one of these is a false positive</h3>
		<div class="table-wrap">
			<table>
				<thead><tr><th>ID</th><th>Class</th><th>Where</th><th>Why it is not a finding</th></tr></thead>
				<tbody>
					{#each negative as n}
						<tr>
							<td class="mono">{n.id}</td>
							<td><span class="badge">{n.class}</span></td>
							<td class="mono">{where(n.where)}</td>
							<td class="faint small">{n.note ?? ''}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
{/if}

{#if t.kind !== 'mobile'}
	<h2>
		Logs
		<button class="btn sm" onclick={toggleTail} style="margin-left:8px"
			>{tailing ? 'Stop' : 'Tail'}</button
		>
	</h2>
	{#if tailing || logs.length}
		<pre class="logs">{logs.join('\n') || 'waiting…'}</pre>
	{:else}
		<p class="faint small">Not tailing.</p>
	{/if}
{/if}

<style>
	.back {
		display: inline-block;
		margin-bottom: 12px;
	}
	.head {
		display: flex;
		align-items: center;
		gap: 9px;
		margin-bottom: 6px;
	}
	.spacer {
		flex: 1;
	}
	.lede {
		max-width: 76ch;
		margin: 0 0 16px;
		font-size: 13.5px;
	}
	.credit {
		border: 1px solid var(--border);
		border-left: 3px solid var(--accent);
		border-radius: var(--radius);
		padding: 12px 15px;
		background: var(--surface);
		margin-bottom: 14px;
	}
	.ct {
		display: flex;
		gap: 14px;
		padding: 3px 0;
		font-size: 13px;
		align-items: baseline;
	}
	.ck {
		color: var(--ink-3);
		width: 82px;
		flex: none;
		font-size: 12px;
	}
	.facts {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
		margin-bottom: 14px;
	}
	.keybar {
		display: flex;
		align-items: center;
		margin-bottom: 8px;
	}
	.check {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 12.5px;
		color: var(--ink-2);
	}
	tr.dimmed {
		opacity: 0.5;
	}
	.logs {
		background: var(--surface-2);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		padding: 12px;
		max-height: 420px;
		overflow: auto;
		font-family: var(--mono);
		font-size: 11.5px;
		line-height: 1.55;
		white-space: pre-wrap;
		margin: 0;
	}
</style>
