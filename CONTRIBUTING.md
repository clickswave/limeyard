# Contributing

limeyard is a measuring instrument. Everything in it exists so a number about a
scanner can be trusted, which makes correctness here worth more than coverage.
A target nobody can reproduce, or an answer key that is subtly wrong, does more
damage than a missing feature: it produces a score that looks fine.

Two things follow from that, and they shape everything below. Credit the people
whose software this lab runs. Be precise about what is true of a target.

## The rule that is not negotiable

Every target names its author and its licence, in `target.yml`, before it
exists. `./lime doctor` fails while an author is missing and the manager
refuses to register the target at all. limeyard is almost entirely other
people's work and the credits page is how they are thanked.

## What a contribution usually is

**A correction to an answer key.** The most valuable thing you can send. If a
`truth.yml` says a target is vulnerable at a path where it is not, every scan
scored against it is wrong in a way nobody notices. Corrections are welcome even
when they lower our own scores, and several already have.

**A new target.** Something a scanner should be able to find, that nothing in
the fleet covers yet.

**A scenario.** Several targets wired into a topology with its own DNS, for the
engines that discover assets rather than test one host.

**The control plane or the panel.** The daemon in `control/limed`, the SvelteKit
panel in `control/ui`.

## Before you open a pull request

```sh
./lime audit     # container hardening and supply chain invariants
./lime doctor    # environment, attribution, answer keys
```

Both must pass. CI runs the same two, builds the panel, and runs `install.sh`
end to end against your branch, so a pull request that fails locally fails
there too.

## Adding a target

```
targets/<kind>/<slug>/
  target.yml    manifest, including a REQUIRED upstream block
  compose.yml   the containers
  setup.sh      optional one-time init, run after start
  truth.yml     the answer key
```

Kinds are `web api bench cve service estate edge control mobile`. Pick the port
from the range for the kind, listed in the README.

**Do not vendor third-party source.** Put `repo:` and `compose:` in the manifest
and the source is cloned into `<target>/src` at first start instead. A copy of
someone else's project in our tree is a fork we did not mean to maintain.

**Bind only to `127.0.0.1`, and only the port the target serves.** The audit
fails on anything else. This lab must never be reachable from another machine.

**Networks.** A single-container target joins `[lime-web]` and nothing else. A
target with a database joins `[default, lime-web]` and puts the database on
`[default]` only, so it gets its own network and volume. A target that exists to
be discovered rather than browsed joins `[lime-lab]` with a static IP and
publishes no host port.

**Hardening is mechanical, not a matter of taste.** Every service needs
`cap_drop: [ALL]`, `security_opt: ["no-new-privileges:true"]`, a pid limit and a
memory limit, and adds back only the capabilities its image actually needs. The
audit lists what is missing. `SECURITY.md` explains why each one is there.

**Pin every image to a digest.** `./lime pin --apply` rewrites the tags to the
digests you pulled and tested. A floating tag means the target can change under
us without a commit.

**Record what it costs.** Start the target on its own, let it settle, then:

```sh
./lime measure <slug>
```

That prints the `resources` block to paste into `target.yml`. The installer and
the panel add these up to tell someone what a selection will do to their machine
before it happens, so a guess here becomes a lie there.

## Correcting an answer key

`truth.yml` is the contract; `vulns/*.md` is the narrative. When they disagree
the YAML is what the scorer believes. The full shape is in
[truth/schema.md](truth/schema.md).

**Ids are permanent.** `DV1` is referenced by every scorecard ever saved. Fix
what an entry says; do not renumber it.

**Scope decides whether something counts.** `black-box` is what an
unauthenticated scanner is expected to find. `authed` counts only when the run
seeded credentials. `out-of-scope` never counts and exists to record a real
vulnerability that a scanner is not meant to reach, so nobody relitigates it
next quarter.

**Negatives matter as much as expected findings.** A `negative` entry is
something that looks vulnerable and is not, and reporting it is a false
positive. A fleet where everything is vulnerable can only measure recall, and
recall alone is how a scanner ends up shipping noisy heuristics.

**Say how you know.** Put the proof in `confirm`. A correction that says which
request was sent and what came back can be checked; an assertion cannot.

## Working on the panel

```sh
cd control/ui && npm install
LIMED_URL=http://127.0.0.1:7099 LIME_TOKEN=<from .env> npm run dev   # :7000
```

The daemon can stay in its container. The lockfile is committed, so use
`npm ci` when you want the exact tree CI builds.

## Commits

Subject line is the area, then what changed, in the imperative and lower case:
`truth: railsgoat's password was wrong, and so was its SQLi entry`. The body is
for why, and for what you tried that did not work. Assume the reader is you in
a year, looking for the reason rather than the diff.

## Licensing

limeyard is MIT. Contributions are accepted under the same licence. The targets
keep their own licences, recorded in their manifests and shown on the credits
page; nothing here relicenses anyone else's work.
