<script>
	import { invalidateAll } from '$app/navigation';
	let { data } = $props();
	let busy = $state({});

	async function act(slug, action) {
		busy = { ...busy, [slug]: action };
		await fetch(`/api/scenarios/${slug}/${action}`, { method: 'POST' });
		setTimeout(() => {
			busy = { ...busy, [slug]: null };
			invalidateAll();
		}, 2000);
	}
</script>

<h1>Scenarios</h1>
<p class="sub">
	A scenario wires several targets into a network topology with authoritative DNS, so subdomain
	enumeration, port scanning and service fingerprinting have something real to enumerate. The zone
	file is the answer key: Docker network aliases are deliberately not used, because they never
	appear in a zone transfer and would make the topology disagree with the truth.
</p>

{#each data.scenarios as s}
	<article class="scn">
		<div class="head">
			<strong>{s.name}</strong>
			<span class="pill" class:ok={s.state === 'running'}>{s.state}</span>
			<div class="actions">
				{#if s.state === 'stopped'}
					<button disabled={!!busy[s.slug]} onclick={() => act(s.slug, 'up')}>
						{busy[s.slug] ? 'starting…' : 'up'}
					</button>
				{:else}
					<button disabled={!!busy[s.slug]} onclick={() => act(s.slug, 'down')}>down</button>
				{/if}
			</div>
		</div>
		<p class="desc">{s.description ?? ''}</p>

		{#if s.zones?.length}
			<h3>DNS zones</h3>
			<table>
				<tbody>
					{#each s.zones as z}
						<tr>
							<td class="mono">{z.zone}</td>
							<td class="dim">transfer {z.allow_transfer ? 'open' : 'refused'}</td>
							<td class="dim">{z.note ?? ''}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}

		{#if s.hosts?.length}
			<h3>Hosts</h3>
			<table>
				<thead><tr><th>ip</th><th>names</th><th>ports</th><th>note</th></tr></thead>
				<tbody>
					{#each s.hosts as h}
						<tr>
							<td class="mono">{h.ip}</td>
							<td class="mono">{(h.names ?? []).join(', ')}</td>
							<td class="dim">{(h.ports ?? []).join(', ')}</td>
							<td class="dim">{h.note ?? ''}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}

		{#if s.expected_assets && Object.keys(s.expected_assets).length}
			<h3>Expected assets <span class="dim">what discovery should find</span></h3>
			<table>
				<tbody>
					{#each Object.entries(s.expected_assets) as [k, v]}
						<tr><td class="k">{k}</td><td class="mono">{Array.isArray(v) ? v.join(', ') : v}</td></tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</article>
{/each}

{#if !data.scenarios.length}<p class="dim">No scenarios defined yet.</p>{/if}

<style>
	.sub { color: var(--dim); margin: 0 0 16px; max-width: 76ch; }
	.scn { background: var(--panel); border: 1px solid var(--line); border-radius: 5px; padding: 13px 15px; margin-bottom: 14px; }
	.head { display: flex; align-items: center; gap: 11px; }
	.pill { font-size: 11px; padding: 2px 7px; border-radius: 10px; border: 1px solid var(--line); color: var(--dim); }
	.pill.ok { color: var(--ok); border-color: var(--ok); }
	.actions { margin-left: auto; }
	button { background: var(--panel2); border: 1px solid var(--line); color: var(--ink); padding: 3px 11px; border-radius: 3px; cursor: pointer; font: inherit; font-size: 12px; }
	.desc { color: var(--dim); font-size: 13px; }
	h3 { font-size: 12px; color: var(--dim); text-transform: uppercase; letter-spacing: .07em; margin: 15px 0 6px; }
	table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
	th { text-align: left; color: var(--dim); font-weight: 400; border-bottom: 1px solid var(--line); padding: 4px 8px; }
	td { padding: 4px 8px; border-bottom: 1px solid var(--panel2); }
	.mono { font-size: 12px; }
	.dim { color: var(--dim); }
	.k { color: var(--dim); width: 190px; }
</style>
