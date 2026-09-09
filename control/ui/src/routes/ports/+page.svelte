<script>
	let { data } = $props();
	let clashes = $derived((data.ports.ports ?? []).filter((p) => p.clash));
	let failed = $derived((data.doctor.checks ?? []).filter((c) => !c.ok));
</script>

<div class="head">
	<h1>Ports and health</h1>
	<span class="status {data.doctor.ok ? 'run' : 'stop'}"
		><i class="dot"></i>doctor {data.doctor.ok ? 'pass' : 'fail'}</span
	>
</div>

{#if data.ports.off_loopback?.length}
	<p class="notice crit">
		{data.ports.off_loopback.length} target(s) bound off loopback. This lab is deliberately vulnerable
		and must never be reachable from another machine:
		{data.ports.off_loopback.map((o) => `${o.target}/${o.service} on ${o.bind}`).join(', ')}
	</p>
{/if}
{#if clashes.length}
	<p class="notice crit">{clashes.length} port clash(es) detected.</p>
{/if}

<h2>Host port map</h2>
<div class="table-wrap">
	<table>
		<thead><tr><th>Port</th><th>Owner</th><th class="right">Status</th></tr></thead>
		<tbody>
			{#each data.ports.ports ?? [] as p}
				<tr>
					<td class="mono nowrap">127.0.0.1:{p.port}</td>
					<td class="mono">{p.owners.join(', ')}</td>
					<td class="right"
						>{#if p.clash}<span class="tag alert">clash</span>{:else}<span class="faint small">ok</span
							>{/if}</td
					>
				</tr>
			{/each}
			{#if !(data.ports.ports ?? []).length}<tr><td colspan="3" class="empty">No published ports.</td></tr>{/if}
		</tbody>
	</table>
</div>

<h2>Checks</h2>
<div class="table-wrap">
	<table>
		<thead><tr><th>Check</th><th>Target</th><th>Detail</th><th class="right">Result</th></tr></thead>
		<tbody>
			{#each data.doctor.checks ?? [] as c}
				<tr>
					<td>{c.check}</td>
					<td class="faint">{c.target ?? '—'}</td>
					<td class="faint small">{c.detail ?? ''}</td>
					<td class="right"
						><span class="tag" class:alert={!c.ok}>{c.ok ? 'pass' : 'fail'}</span></td
					>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
{#if failed.length}
	<p class="faint small" style="margin-top:10px">
		{failed.length} failing check(s). <code>./lime doctor</code> prints the same list with fixes.
	</p>
{/if}

<style>
	.head { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
	.notice { margin-bottom: 12px; }
</style>
