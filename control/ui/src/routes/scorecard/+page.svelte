<script>
	let { data } = $props();
	let c = $derived(data.latest);
	let prev = $derived(data.previous);

	const pct = (v) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`);
	function delta(now, before) {
		if (now == null || before == null) return null;
		const d = (now - before) * 100;
		return Math.abs(d) < 0.05 ? null : `${d > 0 ? '+' : ''}${d.toFixed(1)}`;
	}
</script>

<div class="head"><h1>Scorecard</h1></div>
<p class="lede muted">
	Recall is what we found. Precision is what we did not wrongly report.
</p>

{#if !c}
	<p class="notice">
		No scorecards yet. Post findings to <code>/api/score</code> with <code>save: true</code>, or run
		the harness in <code>scripts/limeyard_scan</code>.
	</p>
{:else}
	<div class="metrics">
		{#each [{ k: 'Recall', v: c.totals.recall, s: `${c.totals.detected}/${c.totals.expected} in scope`, d: delta(c.totals.recall, prev?.totals?.recall) }, { k: 'Precision', v: c.totals.precision, s: `${c.totals.false_positive} false positives`, d: delta(c.totals.precision, prev?.totals?.precision) }, { k: 'F1', v: c.totals.f1, s: `${c.tool}`, d: null }] as m}
			<div class="metric">
				<span class="mk">{m.k}</span>
				<span class="mv">{pct(m.v)}</span>
				<span class="ms faint small">{m.s}</span>
				{#if m.d}<span class="md badge {m.d.startsWith('+') ? 'ok' : 'crit'}">{m.d}</span>{/if}
			</div>
		{/each}
		<div class="metric">
			<span class="mk">Unmatched</span>
			<span class="mv">{c.totals.unmatched}</span>
			<span class="ms faint small">undocumented, promote or investigate</span>
		</div>
	</div>

	<h2>By class</h2>
	<div class="table-wrap">
		<table>
			<thead><tr><th>Class</th><th>Found</th><th class="bar">Coverage</th></tr></thead>
			<tbody>
				{#each Object.entries(c.by_class) as [k, v]}
					<tr>
						<td>{k}</td>
						<td class="mono nowrap">{v.detected}/{v.expected}</td>
						<td class="bar"
							><span class="track"
								><span style="width:{v.expected ? (v.detected / v.expected) * 100 : 0}%"></span></span
							></td
						>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	<h2>By target</h2>
	<div class="table-wrap">
		<table>
			<thead>
				<tr><th>Target</th><th>Found</th><th>Missed</th><th>False positives</th><th>Flags</th></tr>
			</thead>
			<tbody>
				{#each Object.entries(c.by_target) as [slug, r]}
					<tr>
						<td><a href="/targets/{slug}">{slug}</a></td>
						<td class="mono nowrap">{r.detected.length}/{r.expected_in_scope}</td>
						<td class="mono small">{r.missed.join(', ') || '—'}</td>
						<td
							>{#if r.false_positives.length}<span class="badge crit"
									>{r.false_positives.length}</span
								>{:else}<span class="faint">—</span>{/if}</td
						>
						<td class="faint small"
							>{#each r.location_flags ?? [] as f}<div>{f.id}: {f.flags.join('; ')}</div>{/each}</td
						>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	{#if data.history.length > 1}
		<h2>History</h2>
		<div class="table-wrap">
			<table>
				<thead><tr><th>When</th><th>Tool</th><th>Recall</th><th>Precision</th></tr></thead>
				<tbody>
					{#each data.history as h}
						<tr>
							<td class="faint small nowrap">{h.generated}</td>
							<td>{h.tool}</td>
							<td class="mono">{pct(h.totals?.recall)}</td>
							<td class="mono">{pct(h.totals?.precision)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
{/if}

<style>
	.lede { max-width: 78ch; margin: 6px 0 18px; font-size: 13px; }
	.metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(178px, 1fr)); gap: 10px; }
	.metric { position: relative; border: 1px solid var(--border); border-radius: var(--radius); padding: 12px 14px; display: flex; flex-direction: column; gap: 1px; background: var(--bg); }
	.mk { font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--ink-3); }
	.mv { font-size: 25px; font-weight: 600; letter-spacing: -0.02em; }
	.md { position: absolute; top: 11px; right: 12px; }
	.bar { width: 34%; }
	.track { display: block; height: 6px; background: var(--surface-2); border-radius: 3px; overflow: hidden; }
	.track span { display: block; height: 100%; background: var(--accent); }
</style>
