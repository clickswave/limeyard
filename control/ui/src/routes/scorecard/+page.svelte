<script>
	import { ratio, delta, when, sortBy, toggleSort } from '$lib/format.js';
	import Th from '$lib/Th.svelte';

	let { data } = $props();
	let cards = $derived(data.history);

	// Which run the top of the page is about. Latest by default; any row in
	// the history can be viewed by clicking its name.
	let viewIdx = $state(0);
	let c = $derived(cards[viewIdx] ?? null);
	let prev = $derived(cards[viewIdx + 1] ?? null);

	// Compare: exactly two ticked rows.
	let picked = $state(new Set());
	let showCompare = $state(false);
	function togglePick(id) {
		const next = new Set(picked);
		next.has(id) ? next.delete(id) : next.add(id);
		picked = next;
		if (next.size !== 2) showCompare = false;
	}
	let pair = $derived.by(() => {
		if (picked.size !== 2) return null;
		const [a, b] = cards.filter((x) => picked.has(x.id)).sort((x, y) => (x.generated < y.generated ? -1 : 1));
		return { a, b };
	});
	let compareHint = $derived(
		picked.size === 0 ? 'Nothing selected.' : picked.size === 1 ? 'Pick one more run.' : picked.size === 2 ? 'Ready.' : 'Too many selected, pick exactly two.'
	);

	const fpTone = (n) => (n === 0 ? 'ok' : n > 0 ? 'bad' : '');
	const dTone = (d, goodUp = true) => (!d ? '' : (d.startsWith('+') === goodUp ? 'ok' : 'bad'));
	const pct = (v) => `${Math.round((v ?? 0) * 100)}%`;

	let csort = $state({ key: null, dir: 1 });
	let tsort = $state({ key: null, dir: 1 });
	let hsort = $state({ key: null, dir: 1 });
	const num = (r, k) => (r[k] == null ? null : Number(r[k]));
	const rowGet = (r, k) => (k === 'name' || k === 'slug' ? r[k] : k === 'missed' ? r.missed.length : num(r, k));

	let classes = $derived(
		sortBy(Object.entries(c?.by_class ?? {}).map(([name, v]) => ({
			name,
			recall: v.recall,
			detected: v.detected ?? 0,
			expected: v.expected ?? 0,
			fp: v.false_positive ?? 0
		})), csort, rowGet)
	);
	let targets = $derived(
		sortBy(Object.entries(c?.by_target ?? {})
			.map(([slug, r]) => ({
				slug,
				recall: r.recall,
				detected: r.detected?.length ?? 0,
				expected: r.expected_in_scope ?? 0,
				fp: r.false_positives?.length ?? 0,
				missed: r.missed ?? [],
				unmatched: r.unmatched?.length ?? 0
			}))
			.sort((x, y) => (y.expected + y.fp) - (x.expected + x.fp) || x.slug.localeCompare(y.slug)), tsort, rowGet)
	);
	let history = $derived(
		sortBy(cards.map((h, i) => ({ h, i })), hsort, (x, k) =>
			k === 'generated' ? x.h.generated : k === 'tool' ? x.h.tool : x.h.totals?.[k] == null ? null : Number(x.h.totals[k]))
	);

	/** Per-target rows where anything moved between two runs. */
	let diffRows = $derived.by(() => {
		if (!pair) return [];
		const A = pair.a.by_target ?? {};
		const B = pair.b.by_target ?? {};
		const slugs = [...new Set([...Object.keys(A), ...Object.keys(B)])].sort();
		const out = [];
		for (const s of slugs) {
			const a = A[s] ?? {};
			const b = B[s] ?? {};
			const da = new Set(a.detected ?? []);
			const db = new Set(b.detected ?? []);
			const gained = [...db].filter((x) => !da.has(x));
			const lost = [...da].filter((x) => !db.has(x));
			const fpa = a.false_positives?.length ?? 0;
			const fpb = b.false_positives?.length ?? 0;
			if (!gained.length && !lost.length && fpa === fpb) continue;
			out.push({ slug: s, a: `${da.size} / ${a.expected_in_scope ?? 0}`, b: `${db.size} / ${b.expected_in_scope ?? 0}`, fpa, fpb, gained, lost });
		}
		return out;
	});
</script>

<svelte:head><title>Scorecard · limeyard</title></svelte:head>

<main class="page">
	<div class="head">
		<h1>Scorecard</h1>
		{#if c}
			<div class="small muted mono">
				{c.tool} · run {when(c.generated)}{prev ? ` · vs ${when(prev.generated)}` : ''}
			</div>
		{/if}
	</div>

	{#if !c}
		<div class="empty" style="margin-top:28px">
			<div class="t">No scorecards yet.</div>
			<div class="s">
				Post findings to <span class="mono">/api/score</span> with <span class="mono">save: true</span>, or run the harness in
				<span class="mono">scripts/limeyard_scan</span>.
			</div>
		</div>
	{:else}
		<div class="metrics">
			<div class="metric">
				<span class="label">Recall</span>
				<div class="big">
					<span class="n">{ratio(c.totals.recall)}</span>
					{#if delta(c.totals.recall, prev?.totals?.recall)}
						<span class="d {dTone(delta(c.totals.recall, prev?.totals?.recall))}">{delta(c.totals.recall, prev?.totals?.recall)}</span>
					{/if}
				</div>
				<div class="s">{c.totals.detected} of {c.totals.expected} expected findings</div>
			</div>
			<div class="metric">
				<span class="label">Precision</span>
				<div class="big">
					<span class="n">{ratio(c.totals.precision)}</span>
					{#if delta(c.totals.precision, prev?.totals?.precision)}
						<span class="d {dTone(delta(c.totals.precision, prev?.totals?.precision))}">{delta(c.totals.precision, prev?.totals?.precision)}</span>
					{/if}
				</div>
				<div class="s"><span class={fpTone(c.totals.false_positive)} style="font-weight:500">{c.totals.false_positive} false positive{c.totals.false_positive === 1 ? '' : 's'}</span></div>
			</div>
			<div class="metric">
				<span class="label">F1</span>
				<div class="big">
					<span class="n">{ratio(c.totals.f1)}</span>
					{#if delta(c.totals.f1, prev?.totals?.f1)}
						<span class="d {dTone(delta(c.totals.f1, prev?.totals?.f1))}">{delta(c.totals.f1, prev?.totals?.f1)}</span>
					{/if}
				</div>
				<div class="s">{c.totals.unmatched} unmatched · {c.totals.out_of_scope} out of scope</div>
			</div>
		</div>

		<p class="lede" style="margin-top:26px;max-width:70ch">
			Recall and precision carry equal weight here. A run that finds everything and invents things is not a better run than one that finds slightly less and invents nothing.
			{#if c.totals.false_positive > 0}
				<strong style="font-weight:600">{c.totals.false_positive === 1 ? 'One false positive is one' : `${c.totals.false_positive} false positives is ${c.totals.false_positive}`} too many.</strong>
				The negatives in each answer key exist so that number can reach zero.
			{:else}
				<strong style="font-weight:600">Zero false positives.</strong> Every negative in every answer key was left alone.
			{/if}
			{#if c.totals.unmatched > 0}
				The {c.totals.unmatched} unmatched findings hit nothing in any answer key: each is either undocumented truth to promote, or noise to investigate.
			{/if}
		</p>

		<section class="block">
			<h2>By vulnerability class</h2>
			<div class="wrap">
				<table style="min-width:820px;margin-top:14px">
					<thead>
						<tr>
							<Th key="name" sort={csort} onsort={(k) => (csort = toggleSort(csort, k))} width="230px">Class</Th>
							<th class="r" style="width:100px;padding-right:14px"><button type="button" class="sortcol" class:active={csort.key === 'recall'} onclick={() => (csort = toggleSort(csort, 'recall'))}>Recall<span class="caret">{csort.key === 'recall' ? (csort.dir === 1 ? '↑' : '↓') : ''}</span></button></th>
							<th></th>
							<Th key="detected" sort={csort} onsort={(k) => (csort = toggleSort(csort, k))} right width="110px">Found</Th>
							<Th key="fp" sort={csort} onsort={(k) => (csort = toggleSort(csort, k))} right width="100px">FP</Th>
						</tr>
					</thead>
					<tbody>
						{#each classes as k (k.name)}
							<tr>
								<td style="font-weight:500">{k.name}</td>
								<td class="r mono small num" style="padding-right:14px">{ratio(k.recall)}</td>
								<td><div class="bar"><span style="width:{pct(k.recall)}"></span></div></td>
								<td class="r small muted num">{k.detected} / {k.expected}</td>
								<td class="r small num {fpTone(k.fp)}" style="font-weight:500">{k.fp}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>

		<section class="block">
			<h2>By target</h2>
			<div class="wrap">
				<table style="min-width:900px;margin-top:14px">
					<thead>
						<tr>
							<Th key="slug" sort={tsort} onsort={(k) => (tsort = toggleSort(tsort, k))} width="200px">Target</Th>
							<th class="r" style="width:100px;padding-right:14px"><button type="button" class="sortcol" class:active={tsort.key === 'recall'} onclick={() => (tsort = toggleSort(tsort, 'recall'))}>Recall<span class="caret">{tsort.key === 'recall' ? (tsort.dir === 1 ? '↑' : '↓') : ''}</span></button></th>
							<th style="width:180px"></th>
							<th class="r" style="width:90px;padding-right:14px"><button type="button" class="sortcol" class:active={tsort.key === 'detected'} onclick={() => (tsort = toggleSort(tsort, 'detected'))}>Found<span class="caret">{tsort.key === 'detected' ? (tsort.dir === 1 ? '↑' : '↓') : ''}</span></button></th>
							<th class="r" style="width:60px;padding-right:14px"><button type="button" class="sortcol" class:active={tsort.key === 'fp'} onclick={() => (tsort = toggleSort(tsort, 'fp'))}>FP<span class="caret">{tsort.key === 'fp' ? (tsort.dir === 1 ? '↑' : '↓') : ''}</span></button></th>
							<th class="r" style="width:90px;padding-right:14px"><button type="button" class="sortcol" class:active={tsort.key === 'unmatched'} onclick={() => (tsort = toggleSort(tsort, 'unmatched'))}>Unmatched<span class="caret">{tsort.key === 'unmatched' ? (tsort.dir === 1 ? '↑' : '↓') : ''}</span></button></th>
							<Th key="missed" sort={tsort} onsort={(k) => (tsort = toggleSort(tsort, k))}>Missed</Th>
						</tr>
					</thead>
					<tbody>
						{#each targets as r (r.slug)}
							<tr class:quiet={!r.expected && !r.fp}>
								<td style="font-weight:500"><a class="quiet" href="/targets/{r.slug}">{r.slug}</a></td>
								<td class="r mono small num" style="padding-right:14px">{ratio(r.recall)}</td>
								<td><div class="bar"><span style="width:{pct(r.recall)}"></span></div></td>
								<td class="r small muted num" style="padding-right:14px">{r.detected} / {r.expected}</td>
								<td class="r small num {fpTone(r.fp)}" style="padding-right:14px;font-weight:500">{r.fp}</td>
								<td class="r small muted num" style="padding-right:14px">{r.unmatched || '—'}</td>
								<td class="mono tiny muted" style="padding-right:0">{r.missed.join(' ') || (r.expected ? 'none' : 'no in-scope entries')}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>

		<section class="block rule" style="padding-top:24px;margin-top:44px">
			<div class="head">
				<h2>History</h2>
				<span class="small muted">Tick two runs to compare them. Click a run to view it above.</span>
			</div>
			<div class="wrap">
				<table style="min-width:760px;margin-top:14px">
					<thead>
						<tr>
							<th style="width:34px"></th>
							<Th key="generated" sort={hsort} onsort={(k) => (hsort = toggleSort(hsort, k))}>Run</Th>
							<th class="r" style="width:120px;padding-right:14px"><button type="button" class="sortcol" class:active={hsort.key === 'recall'} onclick={() => (hsort = toggleSort(hsort, 'recall'))}>Recall<span class="caret">{hsort.key === 'recall' ? (hsort.dir === 1 ? '↑' : '↓') : ''}</span></button></th>
							<th class="r" style="width:120px;padding-right:14px"><button type="button" class="sortcol" class:active={hsort.key === 'precision'} onclick={() => (hsort = toggleSort(hsort, 'precision'))}>Precision<span class="caret">{hsort.key === 'precision' ? (hsort.dir === 1 ? '↑' : '↓') : ''}</span></button></th>
							<th class="r" style="width:120px;padding-right:14px"><button type="button" class="sortcol" class:active={hsort.key === 'f1'} onclick={() => (hsort = toggleSort(hsort, 'f1'))}>F1<span class="caret">{hsort.key === 'f1' ? (hsort.dir === 1 ? '↑' : '↓') : ''}</span></button></th>
							<Th key="false_positive" sort={hsort} onsort={(k) => (hsort = toggleSort(hsort, k))} right width="130px">False positives</Th>
						</tr>
					</thead>
					<tbody>
						{#each history as { h, i } (h.id)}
							<tr style="height:42px" class:viewing={i === viewIdx}>
								<td><input type="checkbox" checked={picked.has(h.id)} onchange={() => togglePick(h.id)} aria-label={h.id} /></td>
								<td>
									<button class="btn link" style="color:inherit;text-decoration:none;font-size:12.5px" onclick={() => (viewIdx = i)}>
										<span class="mono">{when(h.generated)}</span>
										<span class="muted" style="margin-left:8px">{h.tool}</span>
										{#if i === viewIdx}<span class="muted" style="margin-left:8px">viewing</span>{/if}
									</button>
								</td>
								<td class="r mono small num" style="padding-right:14px">{ratio(h.totals?.recall)}</td>
								<td class="r mono small num" style="padding-right:14px">{ratio(h.totals?.precision)}</td>
								<td class="r mono small num" style="padding-right:14px">{ratio(h.totals?.f1)}</td>
								<td class="r small num {fpTone(h.totals?.false_positive)}" style="font-weight:500">{h.totals?.false_positive ?? '—'}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<div style="margin-top:16px;min-height:32px;display:flex;align-items:center;gap:12px">
				<button class="btn" disabled={picked.size !== 2} onclick={() => (showCompare = !showCompare)}>{showCompare ? 'Hide comparison' : 'Compare selected'}</button>
				<span class="small muted">{compareHint}</span>
			</div>

			{#if showCompare && pair}
				<div class="cmp">
					<div class="wrap">
						<table style="min-width:640px">
							<thead>
								<tr>
									<th style="width:200px"></th>
									<th class="r" style="width:180px;padding-right:14px">{when(pair.a.generated)}</th>
									<th class="r" style="width:180px;padding-right:14px">{when(pair.b.generated)}</th>
									<th class="r" style="width:120px">Change</th>
								</tr>
							</thead>
							<tbody>
								{#each [['Recall', 'recall', true], ['Precision', 'precision', true], ['F1', 'f1', true]] as [name, k, goodUp]}
									{@const d = delta(pair.b.totals?.[k], pair.a.totals?.[k])}
									<tr style="height:40px">
										<td style="font-weight:500">{name}</td>
										<td class="r mono small num" style="padding-right:14px">{ratio(pair.a.totals?.[k])}</td>
										<td class="r mono small num" style="padding-right:14px">{ratio(pair.b.totals?.[k])}</td>
										<td class="r mono small num {dTone(d, goodUp)}">{d ?? 'same'}</td>
									</tr>
								{/each}
								{#each [['Found', 'detected'], ['False positives', 'false_positive'], ['Unmatched', 'unmatched']] as [name, k]}
									{@const a = pair.a.totals?.[k] ?? 0}
									{@const b = pair.b.totals?.[k] ?? 0}
									<tr style="height:40px">
										<td style="font-weight:500">{name}</td>
										<td class="r mono small num" style="padding-right:14px">{a}</td>
										<td class="r mono small num" style="padding-right:14px">{b}</td>
										<td class="r mono small num {b === a ? '' : (b > a) === (k === 'detected') ? 'ok' : 'bad'}">{b === a ? 'same' : `${b > a ? '+' : '−'}${Math.abs(b - a)}`}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>

					<h3 style="margin-top:30px">Targets that moved</h3>
					{#if diffRows.length}
						<div class="wrap">
							<table style="min-width:820px;margin-top:12px;font-size:13px">
								<thead>
									<tr>
										<th style="width:180px">Target</th>
										<th style="width:110px">Before</th>
										<th style="width:110px">After</th>
										<th style="width:90px">FP</th>
										<th style="padding-right:0">Findings that changed</th>
									</tr>
								</thead>
								<tbody>
									{#each diffRows as r (r.slug)}
										<tr style="height:auto">
											<td class="cell" style="font-weight:500"><a class="quiet" href="/targets/{r.slug}">{r.slug}</a></td>
											<td class="cell mono small num muted">{r.a}</td>
											<td class="cell mono small num">{r.b}</td>
											<td class="cell mono small num"><span class={fpTone(r.fpb)}>{r.fpb}</span>{#if r.fpa !== r.fpb}<span class="muted"> from {r.fpa}</span>{/if}</td>
											<td class="cell mono tiny" style="padding-right:0">
												{#each r.gained as id}<span class="ok" style="margin-right:8px">+{id}</span>{/each}
												{#each r.lost as id}<span class="bad" style="margin-right:8px">−{id}</span>{/each}
											</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
					{:else}
						<p class="small muted" style="margin-top:10px">No target gained or lost a finding, and no false-positive count changed.</p>
					{/if}
				</div>
			{/if}
		</section>
	{/if}
</main>

<style>
	tr.quiet td { color: var(--ink-4); }
	tr.quiet td a { color: var(--ink-4); }
	tr.viewing { background: var(--surface); }
	.cmp { margin-top: 24px; padding-top: 22px; border-top: 1px solid var(--line); }
</style>
