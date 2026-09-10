## What this changes, and why

<!-- The reason, not the diff. Assume the reader is you in a year. -->

## Checks

<!-- CI runs these too, but a failing branch wastes a round trip. -->

- [ ] `./lime audit` passes
- [ ] `./lime doctor` passes

<!-- Delete whichever sections do not apply. -->

### If this adds or changes a target

- [ ] `upstream` names the author and the licence
- [ ] Images pinned by digest (`./lime pin --apply`)
- [ ] Ports bind `127.0.0.1` only
- [ ] `resources` measured with `./lime measure <slug>`, not estimated
- [ ] No third-party source vendored into the tree

### If this changes an answer key

- [ ] Existing ids kept; scorecards reference them forever
- [ ] `confirm` says how each entry is provable
- [ ] Evidence below: the request sent, and what came back

### If this changes the panel or the daemon

- [ ] `npm run build` succeeds in `control/ui`
- [ ] Checked in a browser, not only in tests
