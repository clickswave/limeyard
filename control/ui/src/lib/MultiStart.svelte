<script>
	let { targets = [], selected = new Set(), onclose, onchanged } = $props();

	let running = $state(false);
	let done = $state(0);
	let total = $state(0);
	let label = $state('');
	let failures = $state([]);

	// A fixture has nothing to run; heavy targets are opt-in because they cost
	// gigabytes; anything already up is not started again.
	const startable = (t) => t.kind !== 'mobile' && t.state === 'stopped';
	const stoppable = (t) => t.kind !== 'mobile' && t.state !== 'stopped';

	let byKind = $derived(
		[...new Set(targets.map((t) => t.kind))].sort().map((kind) => {
			const all = targets.filter((t) => t.kind === kind);
			return {
				kind,
				all,
				ready: all.filter((t) => startable(t) && !t.heavy),
				heavy: all.filter((t) => startable(t) && t.heavy),
				up: all.filter((t) => t.state === 'running').length
			};
		})
	);

	let picked = $derived(targets.filter((t) => selected.has(t.slug)));
	let allLight = $derived(targets.filter((t) => startable(t) && !t.heavy));
	let allHeavy = $derived(targets.filter((t) => startable(t) && t.heavy));
	let allUp = $derived(targets.filter(stoppable));

	/** Small pool: Docker does not enjoy fourteen simultaneous compose ups, and
	 *  a serialised queue would make the panel feel dead. */
	async function run(list, action, what) {
		if (running || !list.length) return;
		running = true;
		failures = [];
		label = what;
		done = 0;
		total = list.length;

		const queue = [...list];
		const worker = async () => {
			while (queue.length) {
				const t = queue.shift();
				try {
					const r = await fetch(`/api/targets/${t.slug}/${action}`, { method: 'POST' });
					if (!r.ok) {
						const j = await r.json().catch(() => ({}));
						failures = [...failures, `${t.slug}: ${j.error ?? r.status}`];
					}
				} catch (e) {
					failures = [...failures, `${t.slug}: ${e.message}`];
				}
				done += 1;
			}
		};
		await Promise.all([worker(), worker(), worker()]);
		running = false;
		onchanged?.();
	}
</script>

<button class="scrim" aria-label="Close" onclick={onclose}></button>
<aside class="panel" aria-label="Bulk actions">
	<div class="phead">
		<strong>Start targets</strong>
		<span class="spacer"></span>
		<button class="btn sm" onclick={onclose}>Close</button>
	</div>

	<div class="pbody">
		{#if running || failures.length}
			<div class="run">
				{#if running}
					<div class="bar"><span style="width:{total ? (done / total) * 100 : 0}%"></span></div>
					<span class="faint small">{label} · {done} of {total}</span>
				{:else}
					<span class="small">Finished {label}. {done} of {total}.</span>
				{/if}
				{#each failures as f}<div class="small fail">{f}</div>{/each}
			</div>
		{/if}

		{#if picked.length}
			<section>
				<h4>Selection</h4>
				<div class="row">
					<span>{picked.length} selected</span>
					<span class="spacer"></span>
					<button
						class="btn primary"
						disabled={running || !picked.filter(startable).length}
						onclick={() => run(picked.filter(startable), 'start', 'starting selection')}
					>
						Start {picked.filter(startable).length}
					</button>
					<button
						class="btn danger"
						disabled={running || !picked.filter(stoppable).length}
						onclick={() => run(picked.filter(stoppable), 'stop', 'stopping selection')}
					>
						Stop {picked.filter(stoppable).length}
					</button>
				</div>
			</section>
		{/if}

		<section>
			<h4>Everything</h4>
			<div class="row">
				<span>All light targets</span>
				<span class="spacer"></span>
				<span class="faint small">{allLight.length} idle</span>
				<button
					class="btn primary"
					disabled={running || !allLight.length}
					onclick={() => run(allLight, 'start', 'starting all light')}>Start</button
				>
			</div>
			{#if allHeavy.length}
				<div class="row">
					<span>Heavy targets<span class="faint small"> · gigabytes each</span></span>
					<span class="spacer"></span>
					<span class="faint small">{allHeavy.length} idle</span>
					<button
						class="btn"
						disabled={running}
						onclick={() => run(allHeavy, 'start', 'starting heavy')}>Start</button
					>
				</div>
			{/if}
			<div class="row">
				<span>Everything running</span>
				<span class="spacer"></span>
				<span class="faint small">{allUp.length} up</span>
				<button
					class="btn danger"
					disabled={running || !allUp.length}
					onclick={() => run(allUp, 'stop', 'stopping all')}>Stop</button
				>
			</div>
		</section>

		<section>
			<h4>By kind</h4>
			{#each byKind as g}
				<div class="row">
					<span>{g.kind}</span>
					<span class="spacer"></span>
					<span class="faint small">
						{g.up}/{g.all.length} up{g.heavy.length ? ` · ${g.heavy.length} heavy` : ''}
					</span>
					{#if g.ready.length}
						<button
							class="btn primary"
							disabled={running}
							onclick={() => run(g.ready, 'start', `starting ${g.kind}`)}
						>
							Start {g.ready.length}
						</button>
					{:else}
						<span class="faint small none">nothing to start</span>
					{/if}
				</div>
			{/each}
			<p class="faint small note">
				Fixtures have nothing to run and heavy targets are never included in a bulk start unless you
				pick them explicitly.
			</p>
		</section>
	</div>

	<div class="pfoot">
		<span class="faint small">Containers take as long as they take; the table updates itself.</span>
	</div>
</aside>

<style>
	.spacer { flex: 1; }
	h4 {
		font-size: 11px;
		font-weight: 600;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: var(--ink-3);
		margin: 18px 18px 6px;
	}
	section:first-of-type h4 { margin-top: 10px; }
	.row {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 8px 18px;
		border-top: 1px solid var(--border);
		font-size: 13px;
	}
	.row:hover { background: var(--surface); }
	.note { margin: 10px 18px 0; line-height: 1.5; }
	.run { padding: 12px 18px; border-bottom: 1px solid var(--border); }
	.bar { height: 3px; background: var(--surface-2); margin-bottom: 7px; }
	.bar span { display: block; height: 100%; background: var(--accent); transition: width .2s ease; }
	.fail { color: var(--stop); margin-top: 4px; }
	.none { padding: 3px 7px; }
</style>
