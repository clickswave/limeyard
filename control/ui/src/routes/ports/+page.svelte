<script>
	import { sortBy, toggleSort, ipKey } from '$lib/format.js';
	import Th from '$lib/Th.svelte';
	let { data } = $props();
	let psort = $state({ key: null, dir: 1 });
	let lsort = $state({ key: null, dir: 1 });
	let ports = $derived(data.ports.ports ?? []);
	let lab = $derived(data.ports.lab ?? []);
	let off = $derived(data.ports.off_loopback ?? []);
	let clashes = $derived(ports.filter((p) => p.clash));

	/** Every host line: scenario hosts with their names, and target services
	 *  that sit on the lab bridge without a DNS name. */
	const hostLabel = (h) => (h.names?.length ? h.names.join(', ') : h.service ? `${h.owner} / ${h.service}` : h.note || 'no name');

	/** One row per owner, so a clash shows as two rows on the same port. */
	let portRows = $derived(
		sortBy(
			ports.flatMap((p) => p.owners.map((o) => ({ port: Number(p.port), clash: p.clash, ...o }))),
			psort,
			(r, k) => (k === 'port' ? r.port : k === 'name' ? (r.name ?? r.slug) : `${r.kind} ${r.port}`)
		)
	);
	let labRows = $derived(
		sortBy(lab, lsort, (h, k) =>
			k === 'ip' ? ipKey(h.ip) : k === 'host' ? hostLabel(h) : h.ports?.length ? Number(String(h.ports[0]).split('/')[0]) : null
		)
	);
</script>

<svelte:head><title>Ports · limeyard</title></svelte:head>

<main class="page">
	<h1>Ports</h1>
	<p class="lede small" style="margin-top:10px">
		Everything the lab binds on localhost, and the addresses that only exist on the lab bridge.
	</p>

	{#if off.length}
		<p class="notice bad">
			{off.length} port{off.length > 1 ? 's' : ''} bound off loopback. This lab is deliberately vulnerable and must never be
			reachable from another machine: {off.map((o) => `${o.target}/${o.service} on ${o.bind}`).join(', ')}.
			<a href="/doctor">Doctor</a> can rewrite them.
		</p>
	{/if}
	{#if clashes.length}
		<p class="notice bad">
			{clashes.length} port clash{clashes.length > 1 ? 'es' : ''}: {clashes.map((p) => `${p.port} (${p.owners.map((o) => o.slug).join(', ')})`).join('; ')}. The second to start loses.
		</p>
	{/if}

	<div class="cols">
		<div>
			<h2 style="font-size:13px">Host ports</h2>
			<table style="margin-top:12px">
				<thead>
					<tr>
						<Th key="port" sort={psort} onsort={(k) => (psort = toggleSort(psort, k))} width="86px">Port</Th>
						<Th key="name" sort={psort} onsort={(k) => (psort = toggleSort(psort, k))}>Target</Th>
						<Th key="kind" sort={psort} onsort={(k) => (psort = toggleSort(psort, k))} right width="84px">Kind</Th>
					</tr>
				</thead>
				<tbody>
					{#each portRows as o (o.port + o.slug + o.service)}
						<tr style="height:38px" class:clash={o.clash}>
							<td class="mono small" style="font-weight:500">{o.port}</td>
							<td class="small">
								<a class="quiet" href="/targets/{o.slug}">{o.name ?? o.slug}</a>
								{#if o.service && o.service !== o.slug}<span class="muted mono tiny" style="margin-left:6px">{o.service}</span>{/if}
								{#if o.clash}<span class="bad tiny" style="margin-left:6px">clash</span>{/if}
							</td>
							<td class="r mono muted" style="font-size:11.5px">{o.kind}</td>
						</tr>
					{:else}
						<tr><td colspan="3" class="muted small" style="padding:20px 0">No published ports.</td></tr>
					{/each}
				</tbody>
			</table>
		</div>
		<div>
			<h2 style="font-size:13px">Lab addresses <span class="muted mono" style="font-weight:400;margin-left:6px">{data.ports.subnet}</span></h2>
			<table style="margin-top:12px">
				<thead>
					<tr>
						<Th key="ip" sort={lsort} onsort={(k) => (lsort = toggleSort(lsort, k))} width="118px">IP</Th>
						<Th key="host" sort={lsort} onsort={(k) => (lsort = toggleSort(lsort, k))}>Host</Th>
						<Th key="ports" sort={lsort} onsort={(k) => (lsort = toggleSort(lsort, k))} right width="110px">Ports</Th>
					</tr>
				</thead>
				<tbody>
					{#each labRows as h (h.ip + h.owner + (h.service ?? ''))}
						<tr style="height:38px">
							<td class="mono small" style="font-weight:500">{h.ip}</td>
							<td class="mono tiny dim" title={h.note ?? ''}>
								{hostLabel(h)}
								{#if h.via === 'scenario'}<span class="muted" style="margin-left:6px">{h.owner}</span>{/if}
							</td>
							<td class="r mono muted" style="font-size:11.5px">{(h.ports ?? []).join(', ') || '-'}</td>
						</tr>
					{:else}
						<tr><td colspan="3" class="muted small" style="padding:20px 0">Nothing on the lab bridge.</td></tr>
					{/each}
				</tbody>
			</table>
		</div>
	</div>
</main>

<style>
	.cols {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(330px, 1fr));
		gap: 48px;
		margin-top: 28px;
		padding-top: 24px;
		border-top: 1px solid var(--line);
	}
	tr.clash td { color: var(--unhealthy); }
</style>
