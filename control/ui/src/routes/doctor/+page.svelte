<script>
	import { invalidateAll } from '$app/navigation';
	import { runFix } from '$lib/actions.js';
	import State from '$lib/State.svelte';

	let { data } = $props();

	// The report on screen: what the loader fetched, replaced by whatever the
	// last fix returned, so a click shows its consequences without a reload.
	let report = $state(null);
	$effect(() => {
		report = data.doctor;
	});

	let rerunning = $state(false);
	let fixing = $state(null); // 'all' | check id
	let results = $state({}); // id -> {ok, message}
	let lastFix = $state(null); // 'all' | id, for the summary line

	let checks = $derived(report?.checks ?? []);
	let summary = $derived(report?.summary ?? { pass: 0, warn: 0, fail: 0 });
	let fixable = $derived(report?.fixable ?? []);
	const fixableOnPage = (c) => c.fix && c.verdict !== 'pass';

	async function rerun() {
		rerunning = true;
		results = {};
		lastFix = null;
		await invalidateAll();
		rerunning = false;
	}

	async function fix(ids) {
		fixing = ids.length === 1 ? ids[0] : 'all';
		lastFix = fixing;
		const { error, data: d } = await runFix(ids);
		if (error) {
			results = { ...results, [fixing]: { ok: false, message: error } };
		} else {
			const next = {};
			for (const r of d.results ?? []) next[r.id] = { ok: r.ok, message: r.message };
			results = next;
			report = d.doctor;
		}
		fixing = null;
	}

	let fixedCount = $derived(Object.values(results).filter((r) => r.ok).length);
	let failedCount = $derived(Object.values(results).filter((r) => !r.ok).length);
</script>

<svelte:head><title>Doctor · limeyard</title></svelte:head>

<main class="page">
	<div class="head">
		<h1>Doctor</h1>
		<div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
			<span class="small muted num">{summary.pass} pass · {summary.warn} warn · {summary.fail} fail</span>
			{#if fixable.length}
				<button class="btn" disabled={!!fixing || rerunning} onclick={() => fix([])}>
					{fixing === 'all' ? 'Fixing…' : `Fix all (${fixable.length})`}
				</button>
			{/if}
			<button class="btn" disabled={!!fixing || rerunning} onclick={rerun}>{rerunning ? 'Checking…' : 'Re-run'}</button>
		</div>
	</div>
	<p class="lede small" style="margin-top:10px">
		Environment, attribution, supply chain and hardening. A check with a Fix button has an unambiguous remedy and applies it in place; the rest need a person.
	</p>

	{#if !report}
		<p class="notice bad">The daemon did not answer. Nothing can be checked until it does.</p>
	{:else}
		{#if lastFix && !fixing && (fixedCount || failedCount)}
			<p class="notice" class:warn={failedCount > 0}>
				{#if lastFix === 'all'}Fix all ran.{/if}
				{fixedCount} {fixedCount === 1 ? 'fix' : 'fixes'} applied{failedCount ? `, ${failedCount} could not be` : ''}. The list below is the re-check.
			</p>
		{/if}

		<div class="rule" style="margin-top:24px">
			{#each checks as c (c.id)}
				{@const r = results[c.id]}
				<div class="row">
					<State state={c.verdict} label={c.verdict} size="12px" />
					<div style="min-width:0;flex:1">
						<div style="font-size:14px;font-weight:500">{c.name}</div>
						<div class="small muted" style="margin-top:2px;text-wrap:pretty">{c.reason}</div>
						{#if c.items?.length}
							<div class="items mono">
								{#each c.items.slice(0, 12) as it}<div>{it}</div>{/each}
								{#if c.items.length > 12}<div class="muted">and {c.items.length - 12} more</div>{/if}
							</div>
						{/if}
						{#if r}
							<div class="tiny" class:ok={r.ok} class:bad={!r.ok} style="margin-top:6px;font-weight:500">{r.ok ? 'Fixed' : 'Could not fix'} · <span style="font-weight:400">{r.message}</span></div>
						{/if}
					</div>
					<div class="side">
						<span class="mono tiny muted">{c.value ?? ''}</span>
						{#if fixableOnPage(c)}
							<button class="btn sm" disabled={!!fixing || rerunning} onclick={() => fix([c.id])} title={c.fix.description}>
								{fixing === c.id ? 'Fixing…' : c.fix.label}
							</button>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	{/if}
</main>

<style>
	.row {
		display: flex;
		gap: 18px;
		align-items: flex-start;
		padding: 14px 0;
		border-bottom: 1px solid var(--line-row);
	}
	.row :global(.st) {
		text-transform: uppercase;
		letter-spacing: 0.05em;
		width: 88px;
		flex: none;
		margin-top: 3px;
	}
	.side {
		display: flex;
		align-items: center;
		gap: 14px;
		flex: none;
		margin-top: 1px;
		min-height: 28px;
	}
	.items {
		margin-top: 8px;
		font-size: 11.5px;
		line-height: 1.6;
		color: var(--ink-2);
		word-break: break-word;
	}
</style>
