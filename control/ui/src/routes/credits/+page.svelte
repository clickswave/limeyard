<script>
	import { byline, licenceRisk } from '$lib/format.js';
	let { data } = $props();
	let grouped = $derived(
		data.credits.reduce((a, c) => {
			(a[c.kind] ??= []).push(c);
			return a;
		}, {})
	);
	let risky = $derived(data.credits.filter((c) => licenceRisk(c.license)));
	let missing = $derived(data.credits.filter((c) => !c.author));
</script>

<h1>Credits</h1>
<p class="sub">
	limeyard runs other people's work. Every target here was written by someone else unless it says
	Clickswave. This page is generated from each target's <code>target.yml</code>, never hand
	maintained, and <code>./lime credits</code> prints the same thing.
</p>

{#if missing.length}
	<p class="alert">
		{missing.length} target{missing.length > 1 ? 's have' : ' has'} no author recorded.
		<code>./lime doctor</code> fails while that is true.
	</p>
{/if}
{#if risky.length}
	<p class="warn">
		{risky.length} of {data.credits.length} targets declare no usable licence. Run them internally, never
		vendor or redistribute them.
	</p>
{/if}

{#each Object.entries(grouped) as [kind, rows]}
	<h2>{kind}</h2>
	<table>
		<thead>
			<tr><th>target</th><th>author</th><th>licence</th><th>verified</th></tr>
		</thead>
		<tbody>
			{#each rows as c}
				<tr>
					<td><a href="/targets/{c.slug}">{c.name}</a></td>
					<td>
						{#if c.author}
							{#if c.repo}
								<a href={c.repo} target="_blank" rel="noreferrer noopener">{byline(c)}</a>
							{:else}{byline(c)}{/if}
						{:else}<span class="bad">MISSING</span>{/if}
					</td>
					<td class:bad={licenceRisk(c.license)}>{c.license}</td>
					<td class="dim">{c.verified || '-'}</td>
				</tr>
			{/each}
		</tbody>
	</table>
{/each}

<style>
	.sub { color: var(--dim); margin: 0 0 14px; max-width: 70ch; }
	.alert { color: var(--crit); border: 1px solid var(--crit); padding: 8px 11px; border-radius: 4px; font-size: 13px; }
	.warn { color: var(--warn); border: 1px solid var(--warn); padding: 8px 11px; border-radius: 4px; font-size: 13px; }
	table { width: 100%; border-collapse: collapse; font-size: 13px; }
	th { text-align: left; color: var(--dim); font-weight: 400; border-bottom: 1px solid var(--line); padding: 5px 8px; }
	td { padding: 5px 8px; border-bottom: 1px solid var(--panel2); }
	td a { text-decoration: none; }
	.bad { color: var(--crit); }
	.dim { color: var(--dim); }
</style>
