<script>
	import { invalidateAll } from '$app/navigation';
	let { data } = $props();
	let busy = $state({});
	let open = $state({});

	async function act(slug, action) {
		busy = { ...busy, [slug]: action };
		await fetch(`/api/scenarios/${slug}/${action}`, { method: 'POST' });
		setTimeout(() => {
			busy = { ...busy, [slug]: null };
			invalidateAll();
		}, 2500);
	}
	const tone = (s) => (s === 'running' ? 'run' : s === 'stopped' ? 'idle' : 'wait');
</script>

<div class="head">
	<h1>Scenarios</h1>
	<span class="faint small">{data.scenarios.length}</span>
</div>
<p class="lede muted">
	Targets wired into a network topology with authoritative DNS. The zone file is the answer key.
</p>

{#each data.scenarios as s}
	<section class="scn">
		<div class="shead">
			<strong>{s.name}</strong>
			<span class="status {tone(s.state)}"><i class="dot"></i>{s.state}</span>
			<span class="spacer"></span>
			{#if s.state === 'stopped'}
				<button class="btn sm primary" disabled={!!busy[s.slug]} onclick={() => act(s.slug, 'up')}>
					{busy[s.slug] ? 'Starting…' : 'Bring up'}
				</button>
			{:else}
				<button class="btn sm" disabled={!!busy[s.slug]} onclick={() => act(s.slug, 'down')}
					>Tear down</button
				>
			{/if}
			<button class="btn sm" onclick={() => (open = { ...open, [s.slug]: !open[s.slug] })}>
				{open[s.slug] ? 'Hide' : 'Topology'}
			</button>
		</div>
		<p class="muted small sdesc">{s.description ?? ''}</p>

		<div class="counts">
			<span class="tag">{s.hosts?.length ?? 0} hosts</span>
			<span class="tag">{s.zones?.length ?? 0} zones</span>
			{#if s.expected_assets?.subdomains_via_axfr}
				<span class="tag">{s.expected_assets.subdomains_via_axfr.length} expected subdomains</span>
			{/if}
		</div>

		{#if open[s.slug]}
			{#if s.zones?.length}
				<h3>DNS zones</h3>
				<div class="table-wrap">
					<table>
						<thead><tr><th>Zone</th><th>Transfer</th><th>Note</th></tr></thead>
						<tbody>
							{#each s.zones as z}
								<tr>
									<td class="mono">{z.zone}</td>
									<td
										><span class="tag">{z.allow_transfer ? 'open' : 'refused'}</span></td
									>
									<td class="faint small">{z.note ?? ''}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}

			{#if s.hosts?.length}
				<h3>Hosts</h3>
				<div class="table-wrap">
					<table>
						<thead><tr><th>IP</th><th>Names</th><th>Ports</th><th>Note</th></tr></thead>
						<tbody>
							{#each s.hosts as h}
								<tr>
									<td class="mono nowrap">{h.ip}</td>
									<td class="mono">{(h.names ?? []).join(', ') || '—'}</td>
									<td class="mono faint nowrap">{(h.ports ?? []).join(', ')}</td>
									<td class="faint small">{h.note ?? ''}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}

			{#if s.expected_assets && Object.keys(s.expected_assets).length}
				<h3>Expected assets <span class="faint" style="font-weight:400">what discovery should find</span></h3>
				<div class="table-wrap">
					<table>
						<tbody>
							{#each Object.entries(s.expected_assets) as [k, v]}
								<tr>
									<td class="akey">{k.replaceAll('_', ' ')}</td>
									<td class="mono small">
										{#if Array.isArray(v)}
											{v.join(', ')}
										{:else if v && typeof v === 'object'}
											{#each Object.entries(v) as [ik, iv]}
												<div>{ik} <span class="faint">→</span> {Array.isArray(iv) ? iv.join(', ') : iv}</div>
											{/each}
										{:else}{v}{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		{/if}
	</section>
{/each}

{#if !data.scenarios.length}<p class="empty">No scenarios defined.</p>{/if}

<style>
	.head { display: flex; align-items: baseline; gap: 10px; }
	.lede { max-width: 78ch; margin: 6px 0 18px; font-size: 13px; }
	.scn { border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 16px; margin-bottom: 14px; background: var(--bg); }
	.shead { display: flex; align-items: center; gap: 9px; }
	.spacer { flex: 1; }
	.sdesc { margin: 7px 0 10px; max-width: 84ch; }
	.counts { display: flex; gap: 6px; }
	.akey { color: var(--ink-2); width: 210px; font-size: 12.5px; }
</style>
