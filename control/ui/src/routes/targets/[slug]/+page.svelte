<script>
	import { onMount, tick } from 'svelte';
	import { shownState, isBusy } from '$lib/live.svelte.js';
	import { actTarget } from '$lib/actions.js';
	import { byline, licenceRisk, staleDays, STALE_AFTER, where, imageParts, clockNow } from '$lib/format.js';
	import State from '$lib/State.svelte';

	let { data } = $props();
	let t = $derived(data.target);
	let s = $derived(t.fixture ? 'fixture' : shownState(t.slug, t.state));
	let busy = $derived(isBusy(t.slug));
	let live_ = $derived(['running', 'starting', 'partial', 'unhealthy'].includes(s.split(' ')[0]));

	let problem = $state('');
	async function act(action) {
		problem = '';
		const err = await actTarget(t.slug, action);
		if (err) problem = err;
	}

	// Answer key.
	let scope = $state('all');
	let showOos = $state(false);
	let expected = $derived(t.truth?.expected ?? []);
	let inScope = $derived(expected.filter((e) => (e.scope ?? 'black-box') !== 'out-of-scope'));
	let outOfScope = $derived(expected.filter((e) => e.scope === 'out-of-scope'));
	let negatives = $derived(t.truth?.negative ?? []);
	let shown = $derived(
		[...inScope.filter((e) => scope === 'all' || (e.scope ?? 'black-box') === scope), ...(showOos ? outOfScope : [])]
	);
	let hasAuthed = $derived(inScope.some((e) => e.scope === 'authed'));

	// Upstream.
	let stale = $derived(staleDays(t.upstream?.verified));
	let isStale = $derived(stale == null || stale > STALE_AFTER);

	// Log tail. Starts by itself: the page exists to watch this target.
	let lines = $state([]);
	let tailing = $state(false);
	let clock = $state('');
	let box;
	let es;
	function startTail() {
		if (es || t.fixture || !t.compose_present) return;
		es = new EventSource(`/api/targets/${t.slug}/logs`);
		es.addEventListener('log', async (e) => {
			lines = [...lines.slice(-600), JSON.parse(e.data).line];
			await tick();
			if (box) box.scrollTop = box.scrollHeight;
		});
		es.onerror = () => {
			es?.close();
			es = null;
			tailing = false;
		};
		tailing = true;
	}
	function stopTail() {
		es?.close();
		es = null;
		tailing = false;
	}
	onMount(() => {
		startTail();
		clock = clockNow();
		const c = setInterval(() => (clock = clockNow()), 1000);
		return () => {
			stopTail();
			clearInterval(c);
		};
	});
</script>

<svelte:head><title>{t.name} · limeyard</title></svelte:head>

<main class="page tight">
	<a class="btn link tiny" href="/">← Targets</a>

	<div class="top">
		<div style="min-width:0">
			<div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
				<h1 style="font-size:22px">{t.name}</h1>
				<State state={s} size="13.5px" />
			</div>
			<div class="mono muted small" style="margin-top:5px">{t.slug} · {t.kind} · {t.heavy ? 'heavy' : 'light'}{t.egress ? ' · needs egress' : ''}</div>
			{#if t.description}<p class="lede" style="margin-top:14px;max-width:62ch">{t.description}</p>{/if}
		</div>
		{#if !t.fixture}
			<div style="display:flex;gap:8px;flex-wrap:wrap;flex:none">
				<button class="btn" disabled={busy} onclick={() => act(live_ ? 'stop' : 'start')}>{live_ ? 'Stop' : 'Start'}</button>
				<button class="btn" disabled={busy} onclick={() => act('restart')}>Restart</button>
				<button class="btn" disabled={busy} onclick={() => act('pull')}>Pull</button>
				<button class="btn" disabled={busy} onclick={() => act('setup')}>Run setup</button>
			</div>
		{/if}
	</div>
	{#if problem}<p class="tiny bad" style="margin-top:10px">{problem}</p>{/if}

	<div class="facts">
		<div class="fact">
			<span class="label">Address</span>
			<div class="v mono">
				{#if t.url}
					<a href={t.url} target="_blank" rel="noreferrer noopener">{t.url.replace(/^https?:\/\//, '')}</a>
				{:else if t.lab_ips?.length}
					{#each t.lab_ips as ip}<div>{ip}</div>{/each}
				{:else if t.fixture}
					<span class="muted">{t.artifact?.type ?? 'artifact'} fixture, nothing listens</span>
				{:else}
					<span class="muted">lab network only</span>
				{/if}
			</div>
			{#if t.ports?.length > 1}
				<div class="sub mono">{t.ports.map((p) => `${p.port} ${p.service}`).join(' · ')}</div>
			{/if}
		</div>
		<div class="fact">
			<span class="label">Credentials</span>
			<div class="v mono">
				{#if t.credentials?.length}
					{#each t.credentials as c}
						<div>{c.user} / {c.pass}{c.role ? ` · ${c.role}` : ''}</div>
					{/each}
				{:else}<span class="muted">none seeded</span>{/if}
			</div>
			{#if Object.keys(t.session_cookies ?? {}).length}
				<div class="sub mono">cookies: {Object.entries(t.session_cookies).map(([k, v]) => `${k}=${v}`).join('; ')}</div>
			{/if}
		</div>
		<div class="fact">
			<span class="label">Stack</span>
			<div class="v">{t.stack ?? '—'}</div>
		</div>
		{#if t.resources && !t.fixture}
			<div class="fact">
				<span class="label">Footprint</span>
				<div class="v num">{t.resources.containers} {t.resources.containers === 1 ? 'container' : 'containers'} · {t.resources.ram_mb} MB RAM · {t.resources.disk_gb} GB images</div>
				<div class="sub">{t.resources.guess ? 'not measured yet, guessed high' : 'measured idle on the reference box'}{t.disk ? ` · ${t.disk}` : ''}</div>
			</div>
		{/if}
		<div class="fact">
			<span class="label">Upstream</span>
			<div class="v">
				{#if byline(t.upstream)}
					{byline(t.upstream)}{#if t.upstream.repo} · <a href={t.upstream.repo} target="_blank" rel="noreferrer noopener">repo</a>{/if}{#if t.upstream.homepage} · <a href={t.upstream.homepage} target="_blank" rel="noreferrer noopener">site</a>{/if}
				{:else}<span class="bad">author missing from target.yml</span>{/if}
			</div>
			<div class="sub" class:bad={licenceRisk(t.upstream?.license)}>
				{t.upstream?.license}{licenceRisk(t.upstream?.license) ? ' · run internally only, never redistribute' : ''}
			</div>
			{#if t.upstream?.note}<div class="sub">{t.upstream.note}</div>{/if}
		</div>
		<div class="fact">
			<span class="label">Last verified</span>
			<div class="v">{t.upstream?.verified || 'never'}</div>
			{#if isStale}
				<div class="sub warn" style="font-weight:500">Stale. {stale == null ? 'Never checked' : `${stale} days`}, worth confirming it still builds.</div>
			{:else if stale != null}
				<div class="sub">{stale === 0 ? 'today' : stale === 1 ? 'yesterday' : `${stale} days ago`}</div>
			{/if}
		</div>
		{#if t.images?.length}
			<div class="fact">
				<span class="label">Image{t.images.length > 1 ? 's' : ''}</span>
				<div class="v mono tiny">
					{#each t.images as im}
						{@const p = imageParts(im.image)}
						<div title={im.image}>
							{p.name}
							{#if p.short}<span class="muted">@{p.short}</span>{:else}<span class="warn">unpinned</span>{/if}
						</div>
					{/each}
				</div>
			</div>
		{/if}
		{#if t.setup}
			<div class="fact" style="grid-column:1 / -1">
				<span class="label">Setup</span>
				<div class="v" style="max-width:80ch">{t.setup}</div>
			</div>
		{/if}
	</div>

	{#if !t.fixture}
		<section class="block" style="margin-top:38px">
			<div class="head">
				<h2>Log</h2>
				<div style="display:flex;align-items:center;gap:12px">
					<span class="tiny muted">{tailing ? `tailing · ${clock}` : t.compose_present ? 'paused' : 'compose not present'}</span>
					{#if t.compose_present}
						<button class="btn sm" onclick={tailing ? stopTail : startTail}>{tailing ? 'Pause' : 'Resume'}</button>
						<button class="btn sm" onclick={() => (lines = [])}>Clear</button>
					{/if}
				</div>
			</div>
			<div class="log" bind:this={box}>
				{#if lines.length}
					{#each lines as l}<div>{l}</div>{/each}
				{:else}
					<div class="waiting">{tailing ? 'waiting for output' : 'nothing captured'}</div>
				{/if}
			</div>
		</section>
	{/if}

	<section class="block">
		<div class="head">
			<h2>Answer key</h2>
			<div class="small muted num">
				{#if t.has_truth}
					{inScope.length} expected in scope · {outOfScope.length} out of scope · {negatives.length} negatives
				{:else}no truth.yml{/if}
			</div>
		</div>

		{#if !t.has_truth}
			<p class="notice">This target ships no answer key, so it cannot be scored. Add a truth.yml; the shape is in truth/schema.md.</p>
		{:else}
			{#if t.truth?.note}<p class="lede small" style="margin-top:10px">{t.truth.note}</p>{/if}

			<div class="tabs" style="margin-top:14px">
				<button class="tab" class:active={scope === 'all'} onclick={() => (scope = 'all')}>All in scope</button>
				<button class="tab" class:active={scope === 'black-box'} onclick={() => (scope = 'black-box')}>Black-box</button>
				{#if hasAuthed}
					<button class="tab" class:active={scope === 'authed'} onclick={() => (scope = 'authed')}>Authed</button>
				{/if}
				{#if outOfScope.length}
					<label class="check" style="margin-left:auto;padding-bottom:6px">
						<input type="checkbox" bind:checked={showOos} /> Show out-of-scope ({outOfScope.length})
					</label>
				{/if}
			</div>

			{#if shown.length}
				<div class="wrap">
					<table style="min-width:820px;font-size:13px;margin-top:12px">
						<thead>
							<tr>
								<th style="width:96px">ID</th>
								<th style="width:170px">Class</th>
								<th style="width:88px">Severity</th>
								<th style="width:104px">Scope</th>
								<th>Location</th>
								<th style="width:220px;padding-right:0">Confirmed by</th>
							</tr>
						</thead>
						<tbody>
							{#each shown as e (e.id)}
								<tr style="height:40px" class:oos={e.scope === 'out-of-scope'}>
									<td class="mono tiny muted">{e.id}</td>
									<td style="font-weight:500">{e.class}</td>
									<td class="small dim">{e.severity ?? '—'}</td>
									<td class="small muted">{e.scope ?? 'black-box'}</td>
									<td class="mono tiny dim">{where(e.where)}</td>
									<td class="small muted" style="padding-right:0">{e.confirm ?? e.note ?? ''}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{:else}
				<p class="notice">
					{outOfScope.length && !showOos
						? 'Every entry here is out of scope. Tick the box above to see them.'
						: 'Nothing scored in this scope. The target is scored on its negatives below.'}
				</p>
			{/if}

			<div class="rule-heavy" style="margin-top:34px;padding-top:22px">
				<h3>Negatives. Do not report these.</h3>
				<p class="small muted" style="margin-top:7px;max-width:70ch;text-wrap:pretty">
					Each of these looks vulnerable and is not. A scanner that reports one takes a false positive against its precision.
				</p>
				{#if negatives.length}
					<div class="wrap">
						<table style="min-width:820px;font-size:13px;margin-top:14px">
							<thead>
								<tr>
									<th style="width:96px">ID</th>
									<th style="width:170px">Looks like</th>
									<th style="width:280px">Where</th>
									<th style="padding-right:0">Why it is not</th>
								</tr>
							</thead>
							<tbody>
								{#each negatives as n (n.id)}
									<tr style="height:40px">
										<td class="mono tiny muted">{n.id}</td>
										<td style="font-weight:500">{n.class ?? '—'}</td>
										<td class="mono tiny dim">{where(n.where)}</td>
										<td class="small dim" style="padding-right:0">{n.note ?? ''}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{:else}
					<p class="small muted" style="margin-top:14px">No negatives recorded. Precision cannot be measured against this target.</p>
				{/if}
			</div>
		{/if}
	</section>
</main>

<style>
	.top {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 32px;
		flex-wrap: wrap;
		margin-top: 16px;
	}
	tr.oos td { color: var(--ink-4); }
</style>
