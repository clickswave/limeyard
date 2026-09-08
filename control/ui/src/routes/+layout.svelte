<script>
	import '$lib/app.css';
	import { page } from '$app/state';
	let { data, children } = $props();

	const nav = [
		{ href: '/', label: 'Targets' },
		{ href: '/scenarios', label: 'Scenarios' },
		{ href: '/scorecard', label: 'Scorecard' },
		{ href: '/ports', label: 'Ports' },
		{ href: '/credits', label: 'Credits' }
	];

	let disk = $derived(data.status?.disk);
	let diskTone = $derived(
		disk?.free_pct == null ? '' : disk.free_pct < 5 ? 'crit' : disk.free_pct < 12 ? 'warn' : ''
	);
</script>

<header>
	<div class="inner">
		<a class="brand" href="/">
			<span class="logo"></span>
			limeyard
		</a>
		<nav>
			{#each nav as n}
				<a href={n.href} class:active={page.url.pathname === n.href}>{n.label}</a>
			{/each}
		</nav>
		<div class="right">
			{#if disk?.free_pct != null}
				<span class="badge {diskTone}" title="host disk free">
					{disk.free_pct}% disk{disk.heavy_blocked ? ' · heavy blocked' : ''}
				</span>
			{/if}
			<span class="badge {data.limedUp ? 'ok' : 'crit'}"
				><i class="dot"></i>{data.limedUp ? 'connected' : 'offline'}</span
			>
		</div>
	</div>
</header>

<main>
	{#if !data.limedUp}
		<p class="notice crit">
			Cannot reach limed. Start it with <code>docker compose up -d</code>, or
			<code>./lime serve</code>.
		</p>
	{/if}
	{@render children()}
</main>

<footer>
	<span>Every target is deliberately vulnerable. Loopback only.</span>
	<span>Targets are other people's work. <a href="/credits">Credits</a>.</span>
</footer>

<style>
	header {
		border-bottom: 1px solid var(--border);
		background: var(--bg);
		position: sticky;
		top: 0;
		z-index: 10;
	}
	.inner {
		max-width: 1240px;
		margin: 0 auto;
		padding: 0 24px;
		height: 52px;
		display: flex;
		align-items: center;
		gap: 28px;
	}
	.brand {
		display: flex;
		align-items: center;
		gap: 8px;
		font-weight: 600;
		font-size: 15px;
		color: var(--ink);
		letter-spacing: -0.01em;
	}
	.brand:hover {
		text-decoration: none;
	}
	.logo {
		width: 9px;
		height: 9px;
		border-radius: 2px;
		background: var(--accent);
	}
	nav {
		display: flex;
		gap: 20px;
	}
	nav a {
		color: var(--ink-2);
		font-size: 13.5px;
		padding: 16px 0;
		border-bottom: 2px solid transparent;
		margin-bottom: -1px;
	}
	nav a:hover {
		color: var(--ink);
		text-decoration: none;
	}
	nav a.active {
		color: var(--ink);
		border-bottom-color: var(--accent);
		font-weight: 500;
	}
	.right {
		margin-left: auto;
		display: flex;
		gap: 8px;
		align-items: center;
	}
	main {
		max-width: 1240px;
		margin: 0 auto;
		padding: 26px 24px 64px;
	}
	main :global(> .notice) {
		margin-bottom: 18px;
	}
	footer {
		max-width: 1240px;
		margin: 0 auto;
		padding: 16px 24px 40px;
		display: flex;
		justify-content: space-between;
		gap: 16px;
		flex-wrap: wrap;
		border-top: 1px solid var(--border);
		color: var(--ink-3);
		font-size: 12px;
	}
</style>
