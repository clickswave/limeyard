<script>
	import { invalidateAll } from '$app/navigation';
	import { onMount } from 'svelte';
	import { byline, licenceRisk } from '$lib/format.js';

	let { data } = $props();

	let kindFilter = $state('');
	let busy = $state({});

	let shown = $derived(
		kindFilter ? data.targets.filter((t) => t.kind === kindFilter) : data.targets
	);
	let grouped = $derived(
		shown.reduce((acc, t) => {
			(acc[t.kind] ??= []).push(t);
			return acc;
		}, {})
	);
	let kindsPresent = $derived([...new Set(data.targets.map((t) => t.kind))].sort());

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

	// State transitions arrive over SSE, so the dashboard reflects a container
	// coming up without anyone reaching for refresh.
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

	const stateClass = (s) =>
		s === 'running' ? 'ok' : s === 'stopped' ? 'idle' : s === 'unhealthy' ? 'crit' : 'warn';
</script>

<h1>Targets</h1>
<p class="sub">
	{data.targets.length} targets across {kindsPresent.length} kinds. Each runs as its own isolated compose
	project.
</p>

<div class="filters">
	<button class:on={kindFilter === ''} onclick={() => (kindFilter = '')}>all</button>
	{#each kindsPresent as k}
		<button class:on={kindFilter === k} onclick={() => (kindFilter = k)}>{k}</button>
	{/each}
</div>

{#each Object.entries(grouped) as [kind, targets]}
	<h2>{kind}</h2>
	<div class="grid">
		{#each targets as t}
			<article class="card">
				<div class="head">
					<a class="name" href="/targets/{t.slug}">{t.name}</a>
					<span class="pill {stateClass(t.state)}">{t.state}</span>
				</div>

				<!-- Attribution sits directly under the name, on the card itself.
				     Not a tooltip, not buried in a detail view. -->
				<div class="by">
					{#if byline(t.upstream)}
						by
						{#if t.upstream.repo}
							<a href={t.upstream.repo} target="_blank" rel="noreferrer noopener"
								>{byline(t.upstream)}</a
							>
						{:else}
							<span>{byline(t.upstream)}</span>
						{/if}
					{:else}
						<span class="missing">author missing from target.yml</span>
					{/if}
					<span class="lic" class:risk={licenceRisk(t.upstream.license)}>
						{t.upstream.license}
					</span>
				</div>

				<p class="desc">{t.description ?? ''}</p>

				<div class="meta">
					{#if t.url}<a class="url" href={t.url} target="_blank" rel="noreferrer noopener"
							>{t.url}</a
						>{/if}
					{#if t.heavy}<span class="chip">heavy</span>{/if}
					{#if t.egress}<span class="chip">egress</span>{/if}
					<span class="chip" class:muted={!t.has_truth}>
						{t.has_truth ? 'answer key' : 'no answer key'}
					</span>
				</div>

				<div class="actions">
					{#if t.state === 'stopped'}
						<button disabled={!!busy[t.slug]} onclick={() => act(t.slug, 'start')}>
							{busy[t.slug] === 'start' ? 'starting…' : 'start'}
						</button>
					{:else}
						<button disabled={!!busy[t.slug]} onclick={() => act(t.slug, 'stop')}>
							{busy[t.slug] === 'stop' ? 'stopping…' : 'stop'}
						</button>
						<button disabled={!!busy[t.slug]} onclick={() => act(t.slug, 'restart')}>restart</button
						>
					{/if}
					<a class="btn" href="/targets/{t.slug}">detail</a>
				</div>
			</article>
		{/each}
	</div>
{/each}

{#if data.targets.length === 0}
	<p class="empty">No targets found. Is <code>LIMEYARD_DIR</code> pointing at the checkout?</p>
{/if}

<style>
	.sub {
		color: var(--dim);
		margin: 0 0 16px;
	}
	.filters {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
		margin-bottom: 6px;
	}
	.filters button {
		background: var(--panel);
		border: 1px solid var(--line);
		color: var(--dim);
		padding: 3px 10px;
		border-radius: 3px;
		cursor: pointer;
		font: inherit;
		font-size: 12px;
	}
	.filters button.on {
		color: var(--bg);
		background: var(--lime);
		border-color: var(--lime);
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
		gap: 12px;
	}
	.card {
		background: var(--panel);
		border: 1px solid var(--line);
		border-radius: 5px;
		padding: 13px 14px;
	}
	.head {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.name {
		font-weight: 700;
		text-decoration: none;
		color: var(--ink);
	}
	.name:hover {
		color: var(--lime);
	}
	.pill {
		margin-left: auto;
		font-size: 11px;
		padding: 2px 7px;
		border-radius: 10px;
		border: 1px solid var(--line);
		color: var(--dim);
	}
	.pill.ok {
		color: var(--ok);
		border-color: var(--ok);
	}
	.pill.warn {
		color: var(--warn);
		border-color: var(--warn);
	}
	.pill.crit {
		color: var(--crit);
		border-color: var(--crit);
	}
	.by {
		margin-top: 3px;
		font-size: 12px;
		color: var(--dim);
	}
	.by a {
		color: #9fb8c9;
		text-decoration: none;
		border-bottom: 1px dotted #56707f;
	}
	.by .missing {
		color: var(--crit);
	}
	.lic {
		margin-left: 7px;
		font-size: 11px;
		padding: 1px 6px;
		border-radius: 3px;
		border: 1px solid var(--line);
	}
	.lic.risk {
		color: var(--crit);
		border-color: var(--crit);
	}
	.desc {
		color: var(--dim);
		font-size: 12.5px;
		margin: 9px 0 10px;
		min-height: 32px;
	}
	.meta {
		display: flex;
		gap: 7px;
		align-items: center;
		flex-wrap: wrap;
		margin-bottom: 11px;
	}
	.url {
		font-size: 12px;
		text-decoration: none;
	}
	.chip {
		font-size: 11px;
		color: var(--dim);
		border: 1px solid var(--line);
		border-radius: 3px;
		padding: 1px 6px;
	}
	.chip.muted {
		opacity: 0.5;
	}
	.actions {
		display: flex;
		gap: 7px;
	}
	.actions button,
	.actions .btn {
		background: var(--panel2);
		border: 1px solid var(--line);
		color: var(--ink);
		padding: 4px 11px;
		border-radius: 3px;
		cursor: pointer;
		font: inherit;
		font-size: 12px;
		text-decoration: none;
	}
	.actions button:hover:not(:disabled),
	.actions .btn:hover {
		border-color: var(--lime);
		color: var(--lime);
	}
	.actions button:disabled {
		opacity: 0.5;
		cursor: default;
	}
	.empty {
		color: var(--dim);
	}
</style>
