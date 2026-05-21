# Adding Third-Party Rust Package Support to Bottlerocket

## Overview

This document describes two approaches for building third-party Rust packages in Bottlerocket's twoliter build system.
Both use `aws-clock-bound` as a running example.

| | Option 1: Vendored Bundle | Option 2: Workspace Integration |
|---|---|---|
| **Approach** | Self-contained vendored tarball, like Go packages | Release tarball sources added to workspace |
| **Dependency tracking** | Isolated per-package | Unified with all first-party Rust |
| **Hygiene (clippy, deny, fmt)** | Manual/separate | Automatic — same as first-party |
| **Build macros** | Custom `cargo build --offline` | Custom `cargo build --offline` with workspace vendor |
| **Tooling required** | `rustmod.rs`, `docker-cargo` in twoliter | Dependency shim + patch files |
| **Upstream sync** | Re-vendor on update | Update shim deps, refresh patches |
| **Dependency deduplication** | None — each package vendors its own | Full — shared Cargo.lock across workspace |
| **When to choose** | Quick integration, minimal workspace impact | Long-lived packages that should share dependency hygiene |

---

## Option 1: Vendored Bundle (Go-Style)

This approach mirrors how Go third-party packages work.
The package downloads an upstream release tarball and bundles all Cargo dependencies into a separate vendored tarball.
Builds are fully self-contained and offline.

### Twoliter Changes

#### manifest.rs — Added Rust Bundle Module Variant
- Added `Rust` variant to `BundleModule` enum
- Enables `bundle-modules = ["rust"]` in package Cargo.toml

#### rustmod.rs — New Rust Vendoring Module
- Created new module mirroring `gomod.rs` architecture
- Implements `RustMod::vendor()` function that:
  - Extracts source tarball
  - Runs `cargo vendor --locked` inside SDK container
  - Creates bundled tarball with `vendor/` and `.cargo/config.toml`
- Key difference from Go: Rust bundles BOTH `vendor/` AND `.cargo/config.toml`

#### docker-cargo Script
- New bash script added to `twoliter/embedded/`
- Runs cargo commands in Bottlerocket SDK container
- Arguments: `--module-path`, `--sdk-image`, `--cargo-home`, `--command`

#### embedded-bundle/build.rs
- Added `docker-cargo` to the list of embedded tools

### Test Package: aws-clock-bound

Created test package in `kits/bottlerocket-core-kit/packages/aws-clock-bound/` with:

#### Cargo.toml
```toml
[[package.metadata.build-package.external-files]]
url = "https://github.com/aws/clock-bound/archive/refs/tags/3.0.0-alpha.1.tar.gz"
sha512 = "17e7015f..."
bundle-modules = ["rust"]
bundle-root-path = "clock-bound-3.0.0-alpha.1"

[build-dependencies]
glibc = { path = "../glibc" }
```

#### aws-clock-bound.spec
- Uses `%setup -a 1` to extract bundled vendor tarball
- Copies `.cargo/config.toml` for offline builds
- Builds with `cargo build --offline --locked`

### Key Technical Details

#### Bundled Tarball Structure
The Rust vendoring creates a tarball containing:
```
vendor/             # All vendored crate sources
.cargo/config.toml  # Cargo config pointing to vendor/
```

Unlike Go vendoring which only outputs `vendor/`, Rust requires both files.

#### Build Flow
1. buildsys detects `bundle-modules = ["rust"]` in Cargo.toml
2. Downloads source tarball to package directory
3. Calls `docker-cargo` to run vendoring script in SDK container
4. Script runs `cargo vendor --locked > .cargo/config.toml`
5. Creates `bundled-{name}.tar.gz` with vendor/ and .cargo/config.toml
6. RPM spec extracts both tarballs and builds offline

### Commits

#### Twoliter Repository
1. `manifest.rs` — Added `BundleModule::Rust` variant
2. `rustmod.rs` — Created Rust vendoring module
3. `main.rs` — Wired up rustmod dispatch
4. `docker-cargo` — Created embedded script
5. `embedded-bundle/build.rs` — Added docker-cargo to embedded tools
6. `rustmod.rs` — Fixed bundled tarball structure (no top-level dir)
7. `rustmod.rs` — Fixed `--module-path` argument name

#### bottlerocket-core-kit Repository
1. Added `aws-clock-bound` package directory
2. Added to workspace `Cargo.toml` members
3. Added to kit `Cargo.toml` build-dependencies
4. Multiple spec file fixes for license paths, debug handling, attribution

### Build Results

```
bottlerocket-aws-clock-bound-3.0.0~alpha.1-1.x86_64.rpm (1.8 MB)
bottlerocket-aws-clock-bound-sbom-3.0.0~alpha.1-1.x86_64.rpm (1.1 MB)
```

Total kit packages: 130 (129 existing + 1 new)

---

## Option 2: Workspace Integration with Dependency Shim

This approach integrates third-party Rust dependencies into the kit's Cargo workspace without checking in upstream source code.
A minimal "dependency shim" declares the same dependencies as the upstream crate, enabling Cargo to resolve and vendor them.
At build time, the real upstream source is fetched as a tarball, patched for workspace compatibility, and built using the workspace's vendored dependencies.

### Motivation

Option 1 treats third-party Rust as a black box — dependencies are vendored in isolation and none of the workspace's hygiene checks apply.
This means:
- Third-party Rust dependencies are invisible to `cargo-deny` (license, advisory, ban checks)
- No clippy or rustfmt enforcement
- Duplicate dependencies across packages (e.g., both the workspace and the vendored bundle ship their own copy of tokio)
- Security advisories in transitive dependencies go undetected

Option 2 solves this by making third-party Rust a workspace member.
All dependencies flow through the shared `Cargo.lock` and `deny.toml`, giving third-party binaries the same hygiene as first-party code.

### Architecture

The key insight is separating dependency resolution (build-time) from source code (fetched at RPM build time):

```
sources/clock-bound/clock-bound/
├── Cargo.toml   # Dependency shim — declares deps, no real code
└── src/lib.rs   # Stub file for workspace compilation

packages/aws-clock-bound/
├── Cargo.toml                      # Package metadata + external-files for tarball
├── aws-clock-bound.spec            # RPM spec: fetch tarball, apply patches, build
├── 0001-workspace-compat.patch     # Cargo.toml patches (versions, edition, etc.)
├── 0002-source-compat.patch        # Source code patches (API compat)
├── clock-bound-Cargo.lock          # Upstream's Cargo.lock for reference
├── clockbound.service              # systemd service
├── clockbound-sysusers.conf        # System user
├── clockbound-tmpfiles.conf        # Runtime directories
└── 80-clockbound.rules             # udev rules
```

The dependency shim ensures `cargo vendor` pulls all needed crates.
The spec file fetches the real source, patches it, and builds against the workspace vendor directory.

### Integration Workflow

#### Step 1: Create the Dependency Shim

Create a minimal crate in `sources/` that declares the same dependencies as the upstream crate (after patching).
This shim has no real code — it exists only for dependency resolution.

`sources/clock-bound/clock-bound/Cargo.toml`:
```toml
# This is a dependency shim for the clock-bound third-party crate.
# It exists solely to ensure Cargo resolves and vendors all dependencies
# needed by the upstream clock-bound daemon. The actual source code is
# fetched from an upstream release tarball at build time and patched
# for workspace compatibility.
#
# Dependencies here MUST match the patched upstream Cargo.toml.
# See packages/aws-clock-bound/0001-workspace-compat.patch for the
# Cargo.toml modifications applied to the upstream source.

[package]
name = "clock-bound"
version = "3.0.0-alpha.1"
edition = "2021"
publish = false
license = "MIT OR Apache-2.0"
description = "Dependency shim for clock-bound upstream crate"

[dependencies]
bon = { version = "3.8.0" }
byteorder = "1"
# ... all dependencies matching the patched upstream Cargo.toml ...
tokio = { version = "~1.43", features = [...], optional = true }
tokio-util = { version = "=0.7.16", features = ["rt"], optional = true }
rand = "0.8"

[features]
default = ["client"]
client = []
daemon = ["dep:clap", "dep:serde", "dep:tokio", ...]
```

`sources/clock-bound/clock-bound/src/lib.rs`:
```rust
// Dependency shim for clock-bound third-party crate.
// Do not add real code here.
```

Register as a workspace member in `sources/Cargo.toml`:
```toml
members = [
    # ... existing members ...
    "clock-bound/clock-bound",
]
```

Add any needed license clarifications to `sources/clarify.toml`.

#### Step 2: Create Workspace Compatibility Patches

Create patch files that will be applied to the upstream source at build time.

`0001-workspace-compat.patch` — Cargo.toml changes:
- Replace `workspace = true` inherited fields with literal values
- Downgrade edition from 2024 to 2021
- Pin dependency versions for workspace compatibility (tokio, rand, tokio-util)
- Remove dev-dependencies (not needed for release builds)

`0002-source-compat.patch` — Source code changes:
- Rewrite `rand::rng()` → `rand::thread_rng()` (rand 0.9 → 0.8 API)
- Rewrite let-chains to nested if-let (edition 2024 → 2021)

These patches are the same changes you would make manually, but captured as reproducible patch files.

#### Step 3: Create the Package

`packages/aws-clock-bound/Cargo.toml`:
```toml
[package]
name = "aws-clock-bound"
version = "0.1.0"
edition = "2021"
publish = false
build = "../build.rs"

[package.metadata.build-package]
source-groups = [
    "clock-bound",
]

[[package.metadata.build-package.external-files]]
path = "clock-bound-v3.0.0-alpha.1.tar.gz"
url = "https://github.com/aws/clock-bound/archive/refs/tags/v3.0.0-alpha.1.tar.gz"
sha512 = "fc439ea7..."

[lib]
path = "../packages.rs"

[build-dependencies]
glibc = { path = "../glibc" }
```

Key points:
- `source-groups` references the dependency shim in `sources/clock-bound/`
- `external-files` declares the upstream tarball to fetch at build time
- No `bundle-modules` — dependencies come from the workspace vendor directory

#### Step 4: Write the Spec File

The spec file orchestrates: fetch tarball → extract → patch → build with workspace vendor.

```spec
%global _cross_first_party 1
%undefine _debugsource_packages

Name: %{_cross_os}aws-clock-bound
Version: 3.0.0~alpha.1
Release: 1%{?dist}
Summary: ClockBound daemon for clock error bound estimation
License: Apache-2.0 OR MIT
URL: https://github.com/aws/clock-bound

# Upstream source tarball
Source0: clock-bound-v3.0.0-alpha.1.tar.gz

# Workspace compatibility patches
Patch0001: 0001-workspace-compat.patch
Patch0002: 0002-source-compat.patch

Source100: clockbound.service
Source101: clockbound-sysusers.conf
Source200: clockbound-tmpfiles.conf
Source201: 80-clockbound.rules

BuildRequires: %{_cross_os}glibc-devel

%description
%{summary}.

%prep
%setup -T -c
%cargo_prep

# Extract only the clock-bound crate from the upstream tarball.
mkdir -p %{_builddir}/clock-bound-build
tar xf %{S:0} -C %{_builddir}/clock-bound-build \
    --strip-components=3 clock-bound-3.0.0-alpha.1/clock-bound/clock-bound

# Apply workspace compatibility patches to extracted source
patch -d %{_builddir}/clock-bound-build -p1 -i %{_sourcedir}/0001-workspace-compat.patch
patch -d %{_builddir}/clock-bound-build -p1 -i %{_sourcedir}/0002-source-compat.patch

%build
cargo build \
    --offline \
    --verbose \
    --release \
    --manifest-path %{_builddir}/clock-bound-build/Cargo.toml \
    -p clock-bound \
    --features daemon \
    --target %{__cargo_target} \
    --target-dir ${HOME}/.cache/clockbound

%install
install -d %{buildroot}%{_cross_sbindir}
install -p -m 0755 ${HOME}/.cache/clockbound/%{__cargo_target}/release/clockbound \
    %{buildroot}%{_cross_sbindir}/clockbound

install -d %{buildroot}%{_cross_unitdir}
install -p -m 0644 %{S:100} %{buildroot}%{_cross_unitdir}/clockbound.service

install -d %{buildroot}%{_cross_sysusersdir}
install -p -m 0644 %{S:101} %{buildroot}%{_cross_sysusersdir}/clockbound.conf

install -d %{buildroot}%{_cross_tmpfilesdir}
install -p -m 0644 %{S:200}...
