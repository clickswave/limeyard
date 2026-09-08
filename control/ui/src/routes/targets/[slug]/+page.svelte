<script>
	import { onMount } from 'svelte';
	import { byline, licenceRisk, staleDays } from '$lib/format.js';

	let { data } = $props();
	let t = $derived(data.target);
	let logs = $state([]);
	let tailing = $state(false);
	let es;

	let stale = $derived(staleDays(t.upstream?.verified));
	let expected = $derived(t.truth?.expected ?? []);
	let inScope = $derived(expected.filter((e) => (e.scope ?? 'black-box') !== 'out-of-scope'));
	let outOfScope = $derived(expected.filter((e) => e.scope === 'out-of-scope'));
	let negative = $derived(t.truth?.negative ?? []);

	function toggleTail() {
		if (tailing) {
			es?.close();
			tailing = false;
			return;
		}
		logs = [];
		es = new EventSource(`/api/targets/${t.slug}/logs`);
		es.addEventListener('log', (e) => {
			const { line } = JSON.parse(e.data);
			logs = [...logs.slice(-400), line];
		});
		tailing = true;
	}
	onMount(() => () => es?.close());

	const where = (w) =>
		!w ? '' : [w.method, w.path, w.param ? `?${w.param}` : '', w.in ? `(${w.in})` : ''].filter(Boolean).join(' ');
</script>

<a class="back" href="/">&larr; all targets</a>
<h1>{t.name} <span class="slug">{t.slug}</span></h1>

<!-- Credit block, above the vulnerability list. Whose work this is comes first. -->
<section class="credit">
	<div class="crow">
		<span class="k">author</span>
		<span class="v">
			{#if byline(t.upstream)}
				{#if t.upstream.repo}
					<a href={t.upstream.repo} target="_blank" rel="noreferrer noopener"
						>{byline(t.upstream)}</a
					>
				{:else}{byline(t.upstream)}{/if}
			{:else}<span class="bad">missing from target.yml</span>{/if}
		</span>
	</div>
	{#if t.upstream?.homepage}
		<div class="crow">
			<span class="k">homepage</span>
			<span class="v"
				><a href={t.upstream.homepage} target="_blank" rel="noreferrer noopener"
					>{t.upstream.homepage}</a
				></span
			>
		</div>
	{/if}
	<div class="crow">
		<span class="k">licence</span>
		<span class="v" class:bad={licenceRisk(t.upstream?.license)}>
			{t.upstream?.license}
			{#if licenceRisk(t.upstream?.license)}
				<em>run internally only, never redistribute</em>
			{/if}
		</span>
	</div>
	{#if t.upstream?.verified}
		<div class="crow">
			<span class="k">verified</span>
			<span class="v" class:warn={stale > 180}>
				{t.upstream.verified}{#if stale != null}
					<em>{stale} days ago{stale > 180 ? ', worth re-checking it still builds' : ''}</em>
				{/if}
			</span>
		</div>
	{/if}
	{#if t.upstream?.note}
		<div class="crow"><span class="k">note</span><span class="v note">{t.upstream.note}</span></div>
	{/if}
</section>

<div class="facts">
	<span class="chip">{t.kind}</span>
	<span class="chip">{t.state}</span>
	{#if t.stack}<span class="chip">{t.stack}</span>{/if}
	{#if t.heavy}<span class="chip">heavy</span>{/if}
	{#if t.url}<a class="chip link" href={t.url} target="_blank" rel="noreferrer noopener">{t.url}</a>{/if}
</div>

{#if t.description}<p class="desc">{t.description}</p>{/if}
{#if t.setup}<p class="setup"><strong>setup</strong> {t.setup}</p>{/if}

{#if t.credentials?.length}
	<h2>Seeded credentials</h2>
	<table>
		<tbody>
			{#each t.credentials as c}
				<tr><td>{c.user}</td><td>{c.pass}</td><td class="dim">{c.role ?? ''}</td></tr>
			{/each}
		</tbody>
	</table>
{/if}

<h2>Answer key <span class="dim">ours, not upstream's</span></h2>
{#if !t.has_truth}
	<p class="dim">No truth.yml. This target cannot be scored.</p>
{:else}
	{#if t.truth?.note}<p class="keynote">{t.truth.note}</p>{/if}
	<table class="truth">
		<thead>
			<tr><th>id</th><th>class</th><th>where</th><th>scope</th><th>confirm</th></tr>
		</thead>
		<tbody>
			{#each inScope as e}
				<tr>
					<td class="id">{e.id}</td>
					<td>{e.class}</td>
					<td class="mono">{where(e.where)}</td>
					<td><span class="scope {e.scope ?? 'black-box'}">{e.scope ?? 'black-box'}</span></td>
					<td class="dim">{e.confirm ?? ''}</td>
				</tr>
			{/each}
			{#each outOfScope as e}
				<tr class="oos">
					<td class="id">{e.id}</td>
					<td>{e.class}</td>
					<td class="mono">{where(e.where)}</td>
					<td><span class="scope out-of-scope">out-of-scope</span></td>
					<td class="dim">{e.note ?? ''}</td>
				</tr>
			{/each}
		</tbody>
	</table>
	<p class="dim small">
		{inScope.length} scored, {outOfScope.length} out of scope (never counted as a miss),
		{negative.length} negative controls (reporting one is a false positive).
	</p>
{/if}

<h2>
	Logs
	<button class="tail" onclick={toggleTail}>{tailing ? 'stop' : 'tail'}</button>
</h2>
{#if tailing || logs.length}
	<pre class="logs">{logs.join('\n')}</pre>
{:else}
	<p class="dim">Not tailing.</p>
{/if}

<style>
	.back {
		font-size: 12px;
		text-decoration: none;
	}
	.slug {
		color: var(--dim);
		font-weight: 400;
		font-size: 14px;
	}
	.credit {
		background: var(--panel);
		border: 1px solid var(--line);
		border-left: 3px solid var(--lime);
		border-radius: 4px;
		padding: 11px 14px;
		margin: 14px 0 16px;
	}
	.crow {
		display: flex;
		gap: 12px;
		padding: 2px 0;
		font-size: 13px;
	}
	.crow .k {
		color: var(--dim);
		width: 78px;
		flex: none;
	}
	.crow .v.bad,
	.bad {
		color: var(--crit);
	}
	.crow .v.warn {
		color: var(--warn);
	}
	.crow .v em {
		color: var(--dim);
		font-style: normal;
		margin-left: 8px;
		font-size: 12px;
	}
	.crow .note {
		color: var(--dim);
		font-size: 12.5px;
	}
	.facts {
		display: flex;
		gap: 7px;
		flex-wrap: wrap;
		margin-bottom: 10px;
	}
	.chip {
		font-size: 11px;
		color: var(--dim);
		border: 1px solid var(--line);
		border-radius: 3px;
		padding: 2px 7px;
	}
	.chip.link {
		color: var(--lime);
		text-decoration: none;
	}
	.desc,
	.setup {
		color: var(--dim);
		font-size: 13px;
		margin: 6px 0;
	}
	.setup strong {
		color: var(--ink);
	}
	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 12.5px;
	}
	th {
		text-align: left;
		color: var(--dim);
		font-weight: 400;
		border-bottom: 1px solid var(--line);
		padding: 5px 8px;
	}
	td {
		padding: 5px 8px;
		border-bottom: 1px solid var(--panel2);
		vertical-align: top;
	}
	.truth .id {
		color: var(--lime);
	}
	.mono {
		font-size: 12px;
	}
	.oos {
		opacity: 0.55;
	}
	.scope {
		font-size: 11px;
		padding: 1px 6px;
		border-radius: 3px;
		border: 1px solid var(--line);
	}
	.scope.authed {
		color: var(--warn);
		border-color: var(--warn);
	}
	.scope.out-of-scope {
		color: var(--dim);
	}
	.dim {
		color: var(--dim);
	}
	.small {
		font-size: 12px;
	}
	.keynote {
		background: var(--panel);
		border: 1px solid var(--line);
		border-radius: 4px;
		padding: 9px 12px;
		color: var(--dim);
		font-size: 12.5px;
	}
	.tail {
		background: var(--panel2);
		border: 1px solid var(--line);
		color: var(--ink);
		padding: 2px 10px;
		border-radius: 3px;
		cursor: pointer;
		font: inherit;
		font-size: 11px;
		margin-left: 10px;
		text-transform: none;
		letter-spacing: 0;
	}
	.logs {
		background: #0a0d0b;
		border: 1px solid var(--line);
		border-radius: 4px;
		padding: 10px;
		max-height: 420px;
		overflow: auto;
		font-size: 11.5px;
		white-space: pre-wrap;
	}
</style>
