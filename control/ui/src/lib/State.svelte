<script>
	/** A coloured dot and the word. Never a pill: it has to read down a column. */
	let { state, label = null, size = null } = $props();
	let key = $derived(String(state ?? '').split(' ')[0]);
</script>

<span class="st" data-st={key} style:font-size={size}><span class="dot"></span>{label ?? state}</span>
