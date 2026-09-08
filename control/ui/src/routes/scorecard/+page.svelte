<script>
	let { data } = $props();
	let c = $derived(data.latest);
	let prev = $derived(data.previous);

	const pct = (v) => (v == null ? '-' : `${(v * 100).toFixed(1)}%`);
	function delta(now, before) {
		if (now == null || before == null) return null;
		const d = (now - before) * 100;
		if (Math.abs(d) < 0.05) return null;
		return `${d > 0 ? '+' : ''}${d.toFixed(1)}`;
	}
</script>

<h1>Scorecard</h1>
<p class="sub">
	Recall is what we found. Precision is what we did not wrongly report. A lab where every target is
	vulnerable can only measure the first, which is how a scanner ends up shipping noisy heuristics,
	so the negative controls in each answer key matter as much as the expected entries.
</p>

{#if !c}
	<p class="dim">
		No scorecards yet. Post findings to <code>/api/score</code> with <code>save: true</code>, or run
		the harness in <code>scripts/limeyard_scan</code>.
	</p>
{:else}
	<div class="headline">
		<div class="metric">
			<span class="lbl">recall</span>
			<span class="big">{pct(c.totals.recall)}</span>
			<span class="sm">{c.totals.detected}/{c.totals.expected} in scope</span>
			{#if delta(c.totals.recall, prev?.totals?.recall)}
				<span class="d" class:up={c.totals.recall > prev.totals.recall}
					>{delta(c.totals.recall, prev.totals.recall)}</span
				>
			{/if}
		</div>
		<div class="metric">
			<span class="lbl">precision</span>
			<span class="big">{pct(c.totals.precision)}</span>
			<span class="sm">{c.totals.false_positive} false positives</span>
			{#if delta(c.totals.precision, prev?.totals?.precision)}
				<span class="d" class:up={c.totals.precision > prev.totals.precision}
					>{delta(c.totals.precision, prev.totals.precision)}</span
				>
			{/if}
		</div>
		<div class="metric">
			<span class="lbl">f1</span>
			<span class="big">{pct(c.totals.f1)}</span>
			<span class="sm">{c.tool} &middot; {c.generated}</span>
		</div>
		<div class="metric">
			<span class="lbl">unmatched</span>
			<span class="big">{c.totals.unmatched}</span>
			<span class="sm">undocumented, promote or investigate</span>
		</div>
	</div>

	<h2>By class</h2>
	<table>
		<tbody>
			{#each Object.entries(c.by_class) as [k, v]}
				<tr>
					<td class="k">{k}</td>
					<td class="mono">{v.detected}/{v.expected}</td>
					<td class="bar">
						<span style="width:{v.expected ? (v.detected / v.expected) * 100 : 0}%"></span>
					</td>
				</tr>
			{/each}
		</tbody>
	</table>

	<h2>By target</h2>
	<table>
		<thead><tr><th>target</th><th>found</th><th>missed</th><th>false positives</th><th>flags</th></tr></thead>
		<tbody>
			{#each Object.entries(c.by_target) as [slug, r]}
				<tr>
					<td><a href="/targets/{slug}">{slug}</a></td>
					<td class="mono">{r.detected.length}/{r.expected_in_scope}</td>
					<td class="miss">{r.missed.join(', ')}</td>
					<td class:bad={r.false_positives.length}>
						{r.false_positives.length || ''}
					</td>
					<td class="dim">
						{#each r.location_flags ?? [] as f}<div>{f.id}: {f.flags.join('; ')}</div>{/each}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>

	{#if data.history.length > 1}
		<h2>History</h2>
		<table>
			<tbody>
				{#each data.history as h}
					<tr>
						<td class="dim">{h.generated}</td>
						<td>{h.tool}</td>
						<td class="mono">recall {pct(h.totals?.recall)}</td>
						<td class="mono">precision {pct(h.totals?.precision)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
{/if}

<style>
	.sub { color: var(--dim); margin: 0 0 16px; max-width: 76ch; }
	.headline { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 11px; }
	.metric { background: var(--panel); border: 1px solid var(--line); border-radius: 5px; padding: 12px 14px; display: flex; flex-direction: column; gap: 2px; position: relative; }
	.lbl { color: var(--dim); font-size: 11px; text-transform: uppercase; letter-spacing: .08em; }
	.big { font-size: 26px; color: var(--lime); }
	.sm { color: var(--dim); font-size: 11.5px; }
	.d { position: absolute; top: 11px; right: 12px; font-size: 12px; color: var(--crit); }
	.d.up { color: var(--ok); }
	table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
	th { text-align: left; color: var(--dim); font-weight: 400; border-bottom: 1px solid var(--line); padding: 5px 8px; }
	td { padding: 5px 8px; border-bottom: 1px solid var(--panel2); vertical-align: top; }
	td a { text-decoration: none; }
	.k { color: var(--dim); width: 200px; }
	.mono { font-size: 12px; }
	.miss { color: var(--warn); }
	.bad { color: var(--crit); }
	.dim { color: var(--dim); }
	.bar { width: 40%; }
	.bar span { display: block; height: 7px; background: var(--lime); border-radius: 2px; }
</style>
