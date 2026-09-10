<script>
	import { byline, licenceRisk, sortBy, toggleSort } from '$lib/format.js';
	import Th from '$lib/Th.svelte';
	let { data } = $props();

	let q = $state('');
	let onlyRisk = $state(false);
	let sort = $state({ key: null, dir: 1 });
	const onsort = (k) => (sort = toggleSort(sort, k));

	let rows = $derived(
		sortBy(data.credits.filter((c) => {
			if (onlyRisk && !licenceRisk(c.license)) return false;
			if (!q) return true;
			return `${c.name} ${c.author ?? ''} ${c.license ?? ''} ${c.kind}`.toLowerCase().includes(q.toLowerCase());
		}), sort, (c, k) => (k === 'name' ? c.name : k === 'author' ? byline(c) : k === 'kind' ? `${c.kind} ${c.name}` : c[k] || null))
	);
	let risky = $derived(data.credits.filter((c) => licenceRisk(c.license)));
	let missing = $derived(data.credits.filter((c) => !c.author));

	const repoLabel = (r) => String(r).replace(/^https?:\/\//, '').replace(/\/$/, '');
</script>

<svelte:head><title>Credits · limeyard</title></svelte:head>

<main class="page">
	<h1>Credits</h1>
	<p class="lede" style="margin-top:12px;max-width:66ch">
		limeyard is almost entirely other people's work. Every target below was written by someone else and is used under the licence named. The lab adds packaging, an answer key and a scorer, and nothing else.
	</p>

	{#if missing.length}
		<p class="notice bad">
			{missing.length} target{missing.length > 1 ? 's have' : ' has'} no author recorded. Doctor fails while that is true.
		</p>
	{/if}
	{#if risky.length}
		<p class="notice warn">
			{risky.length} of {data.credits.length} targets declare no usable licence. Run them internally; never vendor or redistribute.
		</p>
	{/if}

	<div class="toolbar">
		<input class="inp" type="search" placeholder="Search target, author, licence" bind:value={q} style="width:250px;max-width:100%" />
		<label class="check"><input type="checkbox" bind:checked={onlyRisk} /> Licence risk only</label>
	</div>

	<div class="wrap" style="margin-top:20px">
		<table style="min-width:820px">
			<thead>
				<tr>
					<Th key="name" {sort} {onsort} width="230px">Target</Th>
					<Th key="author" {sort} {onsort} width="210px">Author</Th>
					<Th key="license" {sort} {onsort} width="130px">Licence</Th>
					<Th key="verified" {sort} {onsort} width="120px">Verified</Th>
					<Th key="repo" {sort} {onsort}>Repository</Th>
				</tr>
			</thead>
			<tbody>
				{#each rows as c (c.slug)}
					<tr style="height:42px">
						<td>
							<a class="quiet" href="/targets/{c.slug}" style="font-weight:500">{c.name}</a>
							<span class="mono muted" style="font-size:11.5px;margin-left:8px">{c.kind}</span>
						</td>
						<td class="small dim">{byline(c) ?? ''}{#if !c.author}<span class="bad">missing</span>{/if}</td>
						<td class="mono tiny" class:bad={licenceRisk(c.license)} class:muted={!licenceRisk(c.license)}>{c.license}</td>
						<td class="small muted num">{c.verified || '—'}</td>
						<td class="mono tiny" style="padding-right:0">
							{#if c.repo}<a href={c.repo} target="_blank" rel="noreferrer noopener">{repoLabel(c.repo)}</a>{:else}<span class="muted">—</span>{/if}
						</td>
					</tr>
				{:else}
					<tr><td colspan="5" class="muted small" style="padding:24px 0">Nothing matches.</td></tr>
				{/each}
			</tbody>
		</table>
	</div>
</main>
