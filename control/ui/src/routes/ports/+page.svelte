<script>
	let { data } = $props();
	let clashes = $derived(data.ports.ports?.filter((p) => p.clash) ?? []);
</script>

<h1>Ports and health</h1>

{#if data.ports.off_loopback?.length}
	<p class="alert">
		Targets bound off loopback. This lab is deliberately vulnerable and must never be reachable
		from another machine.
	</p>
	<ul>
		{#each data.ports.off_loopback as o}
			<li class="bad">{o.target}/{o.service} on {o.bind}</li>
		{/each}
	</ul>
{/if}

<h2>Host port map</h2>
{#if clashes.length}<p class="alert">{clashes.length} port clash(es) detected.</p>{/if}
<table>
	<thead><tr><th>port</th><th>owner</th></tr></thead>
	<tbody>
		{#each data.ports.ports ?? [] as p}
			<tr class:bad={p.clash}>
				<td class="mono">127.0.0.1:{p.port}</td>
				<td>{p.owners.join(', ')}{p.clash ? '  CLASH' : ''}</td>
			</tr>
		{/each}
	</tbody>
</table>

<h2>Doctor</h2>
<p class={data.doctor.ok ? 'ok' : 'bad'}>{data.doctor.ok ? 'PASS' : 'FAIL'}</p>
<table>
	<tbody>
		{#each data.doctor.checks ?? [] as c}
			<tr>
				<td class={c.ok ? 'ok' : 'bad'}>{c.ok ? 'ok' : '!!'}</td>
				<td>{c.check}{c.target ? ` (${c.target})` : ''}</td>
				<td class="dim">{c.detail ?? ''}</td>
			</tr>
		{/each}
	</tbody>
</table>

<style>
	table { width: 100%; border-collapse: collapse; font-size: 13px; }
	th { text-align: left; color: var(--dim); font-weight: 400; border-bottom: 1px solid var(--line); padding: 5px 8px; }
	td { padding: 5px 8px; border-bottom: 1px solid var(--panel2); }
	.mono { font-size: 12px; }
	.bad { color: var(--crit); }
	.ok { color: var(--ok); }
	.dim { color: var(--dim); }
	.alert { color: var(--crit); border: 1px solid var(--crit); padding: 8px 11px; border-radius: 4px; font-size: 13px; }
	ul { margin: 6px 0 0; padding-left: 18px; font-size: 13px; }
</style>
