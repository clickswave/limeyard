<script>
	/** A column header that sorts. Click once for ascending, again to flip.
	 *  The caret only appears on the active column, so a header row stays as
	 *  quiet as a plain one until something is sorted. */
	let { key, sort, onsort, right = false, width = null, children } = $props();
	let active = $derived(sort?.key === key);
</script>

<th class:r={right} style:width={width} aria-sort={active ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
	<button type="button" class="sortcol" class:active onclick={() => onsort(key)}>
		{@render children()}<span class="caret" aria-hidden="true">{active ? (sort.dir === 1 ? '↑' : '↓') : ''}</span>
	</button>
</th>
