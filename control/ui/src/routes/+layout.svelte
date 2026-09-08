<script>
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
	let diskState = $derived(
		disk?.free_pct == null ? 'unknown' : disk.free_pct < 5 ? 'crit' : disk.free_pct < 12 ? 'warn' : 'ok'
	);
</script>

<div class="shell">
	<header>
		<div class="brand">
			<span class="mark">limeyard</span>
			<span class="tag">security testing lab</span>
		</div>
		<nav>
			{#each nav as n}
				<a href={n.href} class:active={page.url.pathname === n.href}>{n.label}</a>
			{/each}
		</nav>
		<div class="meters">
			{#if disk}
				<span class="meter {diskState}" title="host disk free">
					disk {disk.free_pct}% {disk.heavy_blocked ? '(heavy blocked)' : ''}
				</span>
			{/if}
			<span class="meter {data.limedUp ? 'ok' : 'crit'}">
				limed {data.limedUp ? 'up' : 'unreachable'}
			</span>
		</div>
	</header>

	<div class="danger">
		Everything in this lab is deliberately vulnerable. Local testing only, loopback binds only.
		Never expose it to an untrusted network.
	</div>

	{#if !data.limedUp}
		<div class="offline">
			Cannot reach the limed daemon. Start it with <code>docker compose up -d</code>, or
			<code>./lime serve</code> to run it outside the container.
		</div>
	{/if}

	<main>{@render children()}</main>

	<footer>
		limeyard runs other people's work. Every target credits its author on its card, in its detail
		view and on the <a href="/credits">credits page</a>.
	</footer>
</div>

<style>
	:global(:root) {
		--bg: #0f1210;
		--panel: #171b18;
		--panel2: #1e241f;
		--line: #2b332c;
		--ink: #dfe6e0;
		--dim: #8b968d;
		--lime: #b4d84a;
		--ok: #6bbf59;
		--warn: #d8b34a;
		--crit: #d86a5a;
	}
	:global(body) {
		margin: 0;
		background: var(--bg);
		color: var(--ink);
		font: 14px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
	}
	:global(a) {
		color: var(--lime);
	}
	:global(h1) {
		font-size: 18px;
		margin: 0 0 4px;
	}
	:global(h2) {
		font-size: 14px;
		margin: 26px 0 10px;
		color: var(--dim);
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}
	:global(code) {
		background: var(--panel2);
		padding: 1px 5px;
		border-radius: 3px;
	}
	.shell {
		max-width: 1180px;
		margin: 0 auto;
		padding: 0 20px 60px;
	}
	header {
		display: flex;
		align-items: center;
		gap: 26px;
		padding: 18px 0 14px;
		flex-wrap: wrap;
	}
	.brand .mark {
		color: var(--lime);
		font-weight: 700;
		font-size: 17px;
	}
	.brand .tag {
		color: var(--dim);
		margin-left: 9px;
		font-size: 12px;
	}
	nav {
		display: flex;
		gap: 16px;
	}
	nav a {
		color: var(--dim);
		text-decoration: none;
		padding-bottom: 2px;
		border-bottom: 2px solid transparent;
	}
	nav a.active,
	nav a:hover {
		color: var(--ink);
		border-bottom-color: var(--lime);
	}
	.meters {
		margin-left: auto;
		display: flex;
		gap: 10px;
	}
	.meter {
		font-size: 12px;
		padding: 3px 8px;
		border-radius: 3px;
		border: 1px solid var(--line);
		color: var(--dim);
	}
	.meter.ok {
		color: var(--ok);
	}
	.meter.warn {
		color: var(--warn);
		border-color: var(--warn);
	}
	.meter.crit {
		color: var(--crit);
		border-color: var(--crit);
	}
	.danger {
		background: #2a1714;
		border: 1px solid #5c2f27;
		color: #e7a99d;
		padding: 9px 12px;
		border-radius: 4px;
		font-size: 12.5px;
	}
	.offline {
		margin-top: 10px;
		background: var(--panel);
		border: 1px solid var(--warn);
		color: var(--warn);
		padding: 10px 12px;
		border-radius: 4px;
		font-size: 13px;
	}
	main {
		margin-top: 22px;
	}
	footer {
		margin-top: 50px;
		padding-top: 14px;
		border-top: 1px solid var(--line);
		color: var(--dim);
		font-size: 12px;
	}
</style>
