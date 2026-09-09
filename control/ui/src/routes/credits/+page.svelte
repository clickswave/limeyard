<script>
	import { byline, licenceRisk } from '$lib/format.js';
	let { data } = $props();

	let q = $state('');
	let onlyRisk = $state(false);

	let rows = $derived(
		data.credits.filter((c) => {
			if (onlyRisk && !licenceRisk(c.license)) return false;
			if (!q) return true;
			return `${c.name} ${c.author ?? ''} ${c.license ?? ''} ${c.kind}`
				.toLowerCase()
				.includes(q.toLowerCase());
		})
	);
	let risky = $derived(data.credits.filter((c) => licenceRisk(c.license)));
	let missing = $derived(data.credits.filter((c) => !c.author));
</script>

<div class="head">
	<h1>Credits</h1>
	<span class="faint small">{data.credits.length} targets</span>
</div>
<p class="lede muted">
	Generated from each <code>target.yml</code>. <code>./lime credits</code> prints the same list.
</p>

{#if missing.length}
	<p class="notice crit">
		{missing.length} target{missing.length > 1 ? 's have' : ' has'} no author recorded.
		<code>./lime doctor</code> fails while that is true.
	</p>
{/if}
{#if risky.length}
	<p class="notice warn">
		{risky.length} of {data.credits.length} targets declare no usable licence. Run them internally; never
		vendor or redistribute.
	</p>
{/if}

<div class="toolbar">
	<input type="search" placeholder="Search author, licence, target…" bind:value={q} />
	<label class="check"><input type="checkbox" bind:checked={onlyRisk} /> Licence risk only</label>
</div>

<div class="table-wrap">
	<table>
		<thead>
			<tr><th>Target</th><th>Kind</th><th>Author</th><th>Licence</th><th>Verified</th></tr>
		</thead>
		<tbody>
			{#each rows as c}
				<tr>
					<td><a href="/targets/{c.slug}">{c.name}</a></td>
					<td class="muted small">{c.kind}</td>
					<td>
						{#if c.author}
							{#if c.repo}
								<a href={c.repo} target="_blank" rel="noreferrer noopener">{byline(c)}</a>
							{:else}{byline(c)}{/if}
						{:else}<span class="tag alert">missing</span>{/if}
					</td>
					<td><span class="tag" class:alert={licenceRisk(c.license)}>{c.license}</span></td>
					<td class="faint small nowrap">{c.verified || '—'}</td>
				</tr>
			{/each}
			{#if !rows.length}<tr><td colspan="5" class="empty">Nothing matches.</td></tr>{/if}
		</tbody>
	</table>
</div>

<style>
	.head { display: flex; align-items: baseline; gap: 10px; }
	.lede { max-width: 74ch; margin: 6px 0 16px; font-size: 13px; }
	.toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; }
	.toolbar input[type='search'] { width: 280px; }
	.check { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--ink-2); }
	.notice { margin-bottom: 12px; }
</style>
