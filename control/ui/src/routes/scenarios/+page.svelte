<script>
	import { live, shownScenarioState } from '$lib/live.svelte.js';
	import { actScenario } from '$lib/actions.js';
	import State from '$lib/State.svelte';

	let { data } = $props();
	let problem = $state({});

	const stateOf = (s) => shownScenarioState(s.slug, s.state);
	const up = (s) => ['running', 'starting', 'partial', 'unhealthy'].includes(stateOf(s).split(' ')[0]);
	const busy = (s) => !!live.pending[`scenario:${s.slug}`];

	/** Per-host state: what limed saw for that container, else the scenario's. */
	function hostState(s, h) {
		const st = s.host_states?.[h.ip];
		if (st) return st;
		return up(s) ? stateOf(s) : 'stopped';
	}
	const hostsUp = (s) => (s.hosts ?? []).filter((h) => hostState(s, h) === 'running').length;

	async function act(s, action) {
		problem = { ...problem, [s.slug]: '' };
		const err = await actScenario(s.slug, action);
		if (err) problem = { ...problem, [s.slug]: err };
	}
</script>

<svelte:head><title>Scenarios · limeyard</title></svelte:head>

<main class="page">
	<h1>Scenarios</h1>

	{#each data.scenarios as s (s.slug)}
		{@const st = stateOf(s)}
		<section class="scn">
			<div class="top">
				<div style="min-width:0">
					<div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
						<h2 style="font-size:17px">{s.name}</h2>
						<State state={st} />
					</div>
					{#if s.description}<p class="lede" style="margin-top:11px">{s.description}</p>{/if}
				</div>
				<div style="display:flex;gap:8px;flex:none">
					<button class="btn" disabled={busy(s)} onclick={() => act(s, up(s) ? 'down' : 'up')}>{up(s) ? 'Bring down' : 'Bring up'}</button>
					<button class="btn" disabled={busy(s)} onclick={() => act(s, 'restart')}>Restart</button>
				</div>
			</div>
			{#if problem[s.slug]}<p class="tiny bad" style="margin-top:8px">{problem[s.slug]}</p>{/if}

			<div class="facts" style="border-top:0;padding-top:0;margin-top:26px;grid-template-columns:repeat(auto-fit,minmax(190px,1fr))">
				<div class="fact">
					<span class="label">Resolver</span>
					<div class="v mono">{s.resolver ?? '—'}</div>
					{#if s.resolver_host}<div class="sub mono">{s.resolver_host} from the host</div>{/if}
				</div>
				<div class="fact">
					<span class="label">Zones</span>
					<div class="v mono">
						{#each s.zones ?? [] as z}<div>{z.zone}</div>{:else}—{/each}
					</div>
				</div>
				<div class="fact">
					<span class="label">Subnet</span>
					<div class="v mono">{s.subnet}</div>
				</div>
				<div class="fact">
					<span class="label">Hosts</span>
					<div class="v num">{s.hosts?.length ?? 0} · {hostsUp(s)} running</div>
				</div>
			</div>

			{#if s.zones?.length}
				<div class="wrap" style="margin-top:26px">
					<table style="min-width:760px">
						<thead>
							<tr>
								<th style="width:230px">Zone</th>
								<th style="width:120px">Transfer</th>
								<th style="padding-right:0">What an engine must get right</th>
							</tr>
						</thead>
						<tbody>
							{#each s.zones as z}
								<tr style="height:42px">
									<td class="mono small">{z.zone}</td>
									<td class="small" class:warn={!z.allow_transfer}>{z.allow_transfer ? 'AXFR open' : 'AXFR refused'}</td>
									<td class="small dim" style="padding-right:0;text-wrap:pretty">{z.note ?? ''}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}

			{#if s.hosts?.length}
				<div class="wrap" style="margin-top:30px">
					<table style="min-width:1000px">
						<thead>
							<tr>
								<th style="width:118px">IP</th>
								<th style="width:250px">Hostnames</th>
								<th style="width:120px">Ports</th>
								<th style="width:110px">State</th>
								<th style="padding-right:0">Why it is here</th>
							</tr>
						</thead>
						<tbody>
							{#each s.hosts as h (h.ip)}
								<tr style="height:46px">
									<td class="mono small">{h.ip}</td>
									<td class="mono tiny dim cell">
										{#each h.names ?? [] as n}<div>{n}</div>{:else}<span class="muted">no name</span>{/each}
									</td>
									<td class="mono tiny muted">{(h.ports ?? []).join(', ') || '—'}</td>
									<td><State state={hostState(s, h)} /></td>
									<td class="small dim" style="padding-right:0;text-wrap:pretty">{h.note ?? ''}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}

			{#if s.expected_assets && Object.keys(s.expected_assets).length}
				<details style="margin-top:26px">
					<summary class="small muted">Expected assets, what discovery should report</summary>
					<div class="wrap">
						<table style="margin-top:12px;font-size:13px">
							<tbody>
								{#each Object.entries(s.expected_assets) as [k, v]}
									<tr style="height:auto">
										<td class="cell muted" style="width:220px">{k.replaceAll('_', ' ')}</td>
										<td class="cell mono tiny dim">
											{#if Array.isArray(v)}
												{v.join(', ')}
											{:else if v && typeof v === 'object'}
												{#each Object.entries(v) as [ik, iv]}
													<div>{ik} <span class="muted">·</span> {Array.isArray(iv) ? iv.join(', ') : iv}</div>
												{/each}
											{:else}{v}{/if}
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				</details>
			{/if}
		</section>
	{:else}
		<div class="empty" style="margin-top:26px">
			<div class="t">No scenarios defined.</div>
			<div class="s">Add one under scenarios/&lt;slug&gt;/ with a scenario.yml and a compose.yml.</div>
		</div>
	{/each}
</main>

<style>
	.scn { margin-top: 26px; padding-top: 22px; border-top: 1px solid var(--line); }
	.scn + .scn { margin-top: 44px; }
	.top { display: flex; align-items: flex-start; justify-content: space-between; gap: 32px; flex-wrap: wrap; }
	summary { cursor: pointer; }
</style>
