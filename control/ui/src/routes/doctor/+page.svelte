<script>
	import { invalidateAll } from '$app/navigation';
	import { runFix } from '$lib/actions.js';
	import State from '$lib/State.svelte';
	import FixModal from '$lib/FixModal.svelte';

	let { data } = $props();

	// The report on screen: what the loader fetched, replaced by whatever the
	// last fix returned, so a click shows its consequences without a reload.
	let report = $state(null);
	$effect(() => {
		report = data.doctor;
	});

	let rerunning = $state(false);
	let modal = $state(null); // { checks: [...] } while open
	let running = $state(false);
	let results = $state(null); // id -> {ok, message} for the modal, and the rows after
	let lastRun = $state(null); // {fixed, failed} for the summary line

	let checks = $derived(report?.checks ?? []);
	let summary = $derived(report?.summary ?? { pass: 0, warn: 0, fail: 0 });
	let fixableChecks = $derived(checks.filter((c) => c.fix && c.verdict !== 'pass'));

	async function rerun() {
		rerunning = true;
		results = null;
		lastRun = null;
		await invalidateAll();
		rerunning = false;
	}

	function open(list) {
		results = null;
		modal = { checks: list };
	}

	async function confirm() {
		running = true;
		const ids = modal.checks.map((c) => c.id);
		const { error, data: d } = await runFix(ids);
		const next = {};
		if (error) {
			for (const id of ids) next[id] = { ok: false, message: error };
		} else {
			for (const r of d.results ?? []) next[r.id] = { ok: r.ok, message: r.message };
			report = d.doctor;
		}
		results = next;
		lastRun = {
			fixed: Object.values(next).filter((r) => r.ok).length,
			failed: Object.values(next).filter((r) => !r.ok).length
		};
		running = false;
	}
</script>

<svelte:head><title>Doctor · limeyard</title></svelte:head>

<main class="page">
	<div class="head">
		<h1>Doctor</h1>
		<div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
			<span class="small muted num">{summary.pass} pass · {summary.warn} warn · {summary.fail} fail</span>
			{#if fixableChecks.length}
				<button class="btn" disabled={running || rerunning} onclick={() => open(fixableChecks)}>
					Fix all ({fixableChecks.length})
				</button>
			{/if}
			<button class="btn" disabled={running || rerunning} onclick={rerun}>{rerunning ? 'Checking…' : 'Re-run'}</button>
		</div>
	</div>
	<p class="lede small" style="margin-top:10px">
		Environment, attribution, supply chain and hardening. A check with a Fix button has an unambiguous remedy; you see the exact commands and edits before anything runs. The rest need a person.
	</p>

	{#if !report}
		<p class="notice bad">The daemon did not answer. Nothing can be checked until it does.</p>
	{:else}
		{#if lastRun && !modal}
			<p class="notice" class:warn={lastRun.failed > 0}>
				{lastRun.fixed} {lastRun.fixed === 1 ? 'fix' : 'fixes'} applied{lastRun.failed ? `, ${lastRun.failed} did not resolve the check` : ''}. The list below is the re-check.
			</p>
		{/if}

		<div class="rule" style="margin-top:24px">
			{#each checks as c (c.id)}
				{@const r = results?.[c.id]}
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
						{#if r && !modal}
							<div class="tiny" class:ok={r.ok} class:bad={!r.ok} style="margin-top:6px;font-weight:500">
								{r.ok ? 'Fixed' : 'Not fixed'} · <span style="font-weight:400">{r.message}</span>
							</div>
						{/if}
					</div>
					<div class="side">
						<span class="mono tiny muted">{c.value ?? ''}</span>
						{#if c.fix && c.verdict !== 'pass'}
							<button class="btn sm" disabled={running || rerunning} onclick={() => open([c])} title={c.fix.description}>
								{c.fix.label}
							</button>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	{/if}
</main>

{#if modal}
	<FixModal checks={modal.checks} {running} {results} onconfirm={confirm} onclose={() => (modal = null)} />
{/if}

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
