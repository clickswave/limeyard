<script>
	/** Nothing runs until the person has seen what will run. The daemon
	 *  computed each step from the current state, so this is the actual list
	 *  of commands and file edits, not a description of them. */
	let { checks = [], onconfirm, onclose, running = false, results = null } = $props();

	let done = $derived(results !== null);
	let title = $derived(checks.length === 1 ? checks[0].fix.label : `Fix all · ${checks.length} fixes`);
	let stepCount = $derived(checks.reduce((n, c) => n + (c.fix.steps?.length ?? 0), 0));

	function key(e) {
		if (e.key === 'Escape' && !running) onclose();
	}
</script>

<svelte:window onkeydown={key} />

<button class="scrim" aria-label="Dismiss" tabindex="-1" onclick={() => !running && onclose()}></button>
<div class="modal" role="dialog" aria-modal="true" aria-labelledby="fix-title">
	<div class="mhead">
		<h2 id="fix-title">{done ? 'Result' : title}</h2>
		<span class="small muted num">{done ? '' : `${stepCount} ${stepCount === 1 ? 'step' : 'steps'}`}</span>
	</div>

	<div class="mbody">
		{#if !done}
			<p class="small dim" style="text-wrap:pretty">
				These are the commands and edits that will run, computed from the lab as it is right now. Files changed on disk are tracked by git, so any edit can be reviewed or reverted.
			</p>
		{/if}
		{#each checks as c (c.id)}
			{@const r = results?.[c.id]}
			<section class="fx">
				<div class="fxhead">
					<div>
						<div style="font-weight:500">{c.fix.label} <span class="muted" style="font-weight:400">· {c.name}</span></div>
						<div class="small muted" style="margin-top:2px;text-wrap:pretty">{c.fix.description}</div>
					</div>
					{#if r}
						<span class="st" data-st={r.ok ? 'pass' : 'fail'} style="text-transform:uppercase;letter-spacing:.05em;font-size:12px;flex:none"><span class="dot"></span>{r.ok ? 'fixed' : 'not fixed'}</span>
					{/if}
				</div>
				{#if r}
					<div class="steps"><div>{r.message}</div></div>
				{:else}
					<div class="steps">
						{#each c.fix.steps ?? [] as s}<div>{s}</div>{/each}
					</div>
				{/if}
			</section>
		{/each}
	</div>

	<div class="mfoot">
		{#if done}
			<button class="btn" onclick={onclose}>Close</button>
		{:else}
			<button class="btn" disabled={running} onclick={onclose}>Cancel</button>
			<button class="btn primary" disabled={running} onclick={onconfirm}>
				{running ? 'Running…' : checks.length === 1 ? 'Run fix' : `Run ${checks.length} fixes`}
			</button>
		{/if}
	</div>
</div>

<style>
	.scrim {
		position: fixed; inset: 0; z-index: 40; border: 0; padding: 0; cursor: default;
		background: rgba(28, 28, 25, 0.28);
	}
	.modal {
		position: fixed; z-index: 41; top: 8vh; left: 50%; transform: translateX(-50%);
		width: 720px; max-width: calc(100vw - 32px); max-height: 84vh;
		background: var(--bg); border: 1px solid var(--line-ctl); border-radius: 6px;
		box-shadow: 0 12px 40px rgba(28, 28, 25, 0.14);
		display: flex; flex-direction: column;
	}
	.mhead {
		display: flex; align-items: baseline; justify-content: space-between; gap: 16px;
		padding: 18px 22px 14px; border-bottom: 1px solid var(--line);
	}
	.mbody { padding: 16px 22px; overflow: auto; }
	.fx { margin-top: 18px; }
	.fx:first-of-type { margin-top: 14px; }
	.fxhead { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
	.steps {
		margin-top: 10px; background: var(--surface); border: 1px solid var(--line); border-radius: 4px;
		padding: 10px 13px; font-family: var(--mono); font-size: 12px; line-height: 1.65; color: var(--ink-2);
		white-space: pre-wrap; word-break: break-word;
	}
	.mfoot {
		display: flex; justify-content: flex-end; gap: 8px;
		padding: 14px 22px; border-top: 1px solid var(--line);
	}
	.btn.primary { background: var(--ink); color: var(--bg); border-color: var(--ink); }
	.btn.primary:hover:not(:disabled) { background: var(--ink-2); border-color: var(--ink-2); }
</style>
