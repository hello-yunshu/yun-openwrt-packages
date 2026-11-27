# Promoting pending source locks

`metadata/source-lock.json` is the feed build input contract. A `pending` entry
means there is no public immutable source/release ref for the intended package
state yet. The current CFI, PM, and Rill working trees contain uncommitted or
untracked goal changes, so their local `HEAD` values do not identify those
changes and must not be copied into this file.

## Automatic tracking

The scheduled feed workflow runs `scripts/update_source_lock.py` before every
build. It resolves the newest non-draft, non-prerelease GitHub Release for every
package listed in `metadata/mainstream-support.json`, pins the tag commit and
`PKG_VERSION`, resolves the Rill Runtime through its Stable qualification assets,
and commits `metadata/source-lock.json` only when something moved. Manual
`workflow_dispatch` runs on `main` follow the same path.

Adding a feed package therefore needs no script change and no lock template:
declare it once in the support matrix (`repository`, `path`, `architectures`),
and the next run creates the lock entry, fills `ref`/`packageVersion`, and
promotes it to `locked`. Qualification cells that are not recorded yet are
derived from the declared architectures (`pending` for supported arches,
`unsupported` for the rest), so a support entry without `repository`/`path` is
reported as pending instead of crashing the matrix.

The manual steps below remain the recovery path when automatic resolution cannot
find a public immutable source (for example, a package that must stay pinned).

## Application package sources

After the reviewed package changes are committed and pushed in each source
repository:

1. Record the exact 40-character commit SHA that contains the final package
recipe and its dependencies. For PM, include the sibling data directories read
by `luci-app-performance-manager-all/Makefile` in that same commit.
2. Record the package version beside `ref`. Each SDK-built package can use a
   literal `PKG_VERSION` or a Make expression that reads a single version from
   `VERSION` beside its recipe or at the repository root. The feed reads both inputs from the same
   commit and verifies the built package version. For a root `VERSION` of
   `x.y.z-rc.N`, the recipe must produce the OpenWrt version `x.y.z_rcN`.
   The feed stages each dependency's version beside its SDK recipe, so it can
   share an SDK with plugins from different source repositories. For the
   primary package, a repository-root `VERSION` is also available one and two
   directories above the staged recipe for older recipes.
3. Keep the lock pending if the commit is not retrievable from the declared
   public repository. `build_matrix.py --show-pending` is a read-only preview;
   `--scope all-required` is the fail-closed build gate.

Do not use a local dirty-tree hash, a moving branch name, or an unqualified CI
artifact as a package source lock.

## Rill Runtime artifacts

The feed imports Runtime bytes from a Rill GitHub Release promoted from one
successful `OpenWrt package qualification` run. It does not build or download
`latest` Runtime packages.

1. Commit and push the final `rill-openwrt-packages` changes, including the
   shared `rill-runtime-manager` package.
2. Run the qualification workflow for the selected OpenWrt matrix and retain
   its exact `head_sha`, run ID, and run attempt. The release workflow verifies
   those identities and promotes the package artifacts from that run without
   rebuilding them.
3. After the immutable GitHub Release exists, record its exact tag and numeric
   release ID. Calculate SHA-256 for its `qualification.json` and `SHA256SUMS`
   assets, and set `packageCommit` to the exact Rill repository commit in that
   qualification evidence.
4. Set the `rill-runtime-manager` source ref to that same package commit. The
   feed matrix rejects a manager ref that differs from the commit which
   qualified the Stable Runtime.

After the new Stable qualification succeeds, synchronize the exact Rill
package commit and qualification identity into the CFI and PM consumer
contracts, then update the CFI/PM package matrices to the selected OpenWrt
release and rerun their targeted package-manager jobs.

The feed verifier rechecks the release ID, tag/package identity, evidence
digest, sums digest, all Runtime asset hashes, and the exact six-target × two
release Stable matrix before importing bytes.

## Qualification is separate from source locking

A source lock makes a build repeatable; it does not qualify installation or
device behavior. The automatic feed run records `build-verified` for a cell only
after the exact artifact, digest, source ref, version, and signature all match;
all applicable cells at that level make the candidate publishable. Leave
support-matrix cells `pending` until evidence for the exact package, OpenWrt
release, and architecture covers build, signature, dependency resolution, clean
install, and upgrade; that promotion produces `build-install-qualified`. Mark
device Runtime as `not-evaluated-device` unless device evidence exists.

Run `python3 scripts/validate_mainstream_support.py`,
`python3 scripts/build_matrix.py --show-pending`, and the feed workflow in
`all-required` mode after updating locks. A failure to retrieve an exact source
or release, a package-version mismatch, incomplete qualification evidence, or
a signing-key mismatch must keep the candidate unpublishable.
