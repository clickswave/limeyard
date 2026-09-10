<script>
	import '@fontsource/ibm-plex-sans/400.css';
	import '@fontsource/ibm-plex-sans/500.css';
	import '@fontsource/ibm-plex-sans/600.css';
	import '@fontsource/ibm-plex-mono/400.css';
	import '@fontsource/ibm-plex-mono/500.css';
	import '$lib/app.css';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { live, connect } from '$lib/live.svelte.js';
	import { clockNow } from '$lib/format.js';
	import State from '$lib/State.svelte';

	let { data, children } = $props();

	const nav = [
		{ href: '/', label: 'Targets' },
		{ href: '/scenarios', label: 'Scenarios' },
		{ href: '/scorecard', label: 'Scorecard' },
		{ href: '/ports', label: 'Ports' },
		{ href: '/doctor', label: 'Doctor' },
		{ href: '/credits', label: 'Credits' }
	];

	let clock = $state('');
	onMount(() => {
		const off = connect();
		clock = clockNow();
		const t = setInterval(() => (clock = clockNow()), 1000);
		return () => {
			off();
			clearInterval(t);
		};
	});

	const active = (href) =>
		href === '/'
			? page.url.pathname === '/' || page.url.pathname.startsWith('/targets')
			: page.url.pathname.startsWith(href);

	let disk = $derived(live.disk ?? data.status?.disk);
	let host = $derived(live.host ?? data.status?.host);
	// Colour only when it matters: a machine at 40% CPU is not news.
	const tone = (pct, warn, bad) => (pct == null ? '' : pct >= bad ? 'bad' : pct >= warn ? 'warn' : '');
	let cpuTone = $derived(tone(host?.cpu_pct, 85, 95));
	let ramTone = $derived(tone(host?.ram?.pct, 85, 95));
	let diskTone = $derived(disk?.level === 'crit' ? 'bad' : disk?.level === 'low' ? 'warn' : '');
	let hostTitle = $derived(
		host
			? `load ${host.load1 ?? '?'} on ${host.cpus ?? '?'} cpus · ram ${host.ram?.pct ?? '?'}% used · disk ${disk?.free_pct ?? '?'}% free`
			: ''
	);
	let up = $derived(data.limedUp && (live.connected || live.tick === 0));
</script>

<header>
	<div class="inner">
		<a class="brand" href="/"><span>lime</span><span class="yard">yard</span></a>
		<nav>
			{#each nav as n}
				<a href={n.href} class:active={active(n.href)}>{n.label}</a>
			{/each}
		</nav>
		<div class="right">
			{#if host || disk}
				<a href="/doctor" class="quiet host mono num" title={hostTitle}>
					{#if host?.cpu_pct != null}<span class={cpuTone}>cpu {Math.round(host.cpu_pct)}%</span>{/if}
					{#if host?.ram}<span class={ramTone}>ram {host.ram.used_gb}/{host.ram.total_gb} GB</span>{/if}
					{#if disk?.free_gb != null}<span class={diskTone}>{Math.round(disk.free_gb)} GB free{disk.heavy_blocked ? ' · heavy blocked' : ''}</span>{/if}
				</a>
			{/if}
			<State state={up ? 'running' : 'unhealthy'} label={up ? 'daemon' : 'daemon offline'} size="12.5px" />
			<span class="clock mono num">{clock}</span>
		</div>
	</div>
</header>

{#if !data.limedUp}
	<div class="page" style="padding-bottom:0">
		<p class="notice bad">
			Cannot reach limed. Start the control plane with <span class="mono">docker compose up -d</span>, or run
			<span class="mono">./lime serve</span>.
		</p>
	</div>
{/if}

{@render children()}

<style>
	header {
		border-bottom: 1px solid var(--line);
		background: var(--bg);
		position: sticky;
		top: 0;
		z-index: 5;
	}
	.inner {
		max-width: 1420px;
		margin: 0 auto;
		padding: 0 32px;
		display: flex;
		align-items: center;
		gap: 36px;
		height: 54px;
	}
	.brand {
		display: flex;
		align-items: baseline;
		gap: 1px;
		flex: none;
		text-decoration: none;
		font-size: 16px;
		font-weight: 600;
		letter-spacing: -0.01em;
		color: var(--ink);
	}
	.brand .yard { font-weight: 400; color: var(--accent); }
	nav {
		display: flex;
		gap: 24px;
		align-items: stretch;
		height: 100%;
		flex: 1;
		min-width: 0;
		overflow-x: auto;
	}
	nav a {
		color: var(--ink-3);
		text-decoration: none;
		padding: 8px 0;
		border-bottom: 2px solid transparent;
		font-size: 14px;
		white-space: nowrap;
		display: flex;
		align-items: center;
	}
	nav a:hover { color: var(--ink); }
	nav a.active { color: var(--ink); font-weight: 500; border-bottom-color: var(--accent); }
	.right {
		display: flex;
		align-items: center;
		gap: 14px;
		flex: none;
		font-size: 12.5px;
		color: var(--ink-3);
	}
	.right :global(.st) { color: var(--running); }
	.right :global(.st[data-st='unhealthy']) { color: var(--unhealthy); }
	.clock { font-size: 12.5px; }
	.host { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--ink-3); }
	.host:hover { color: var(--ink); }
	/* A hairline between the three readings, faint enough to be felt, not read. */
	.host span + span { padding-left: 10px; border-left: 1px solid var(--line); }
	.host .warn { color: var(--starting); }
	.host .bad { color: var(--unhealthy); }
	@media (max-width: 900px) { .host span:not(:last-child) { display: none; } }
</style>
