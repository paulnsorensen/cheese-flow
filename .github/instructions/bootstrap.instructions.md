---
applyTo: "bootstrap.sh"
---

## Bootstrap supply-chain review — strictest tier

`bootstrap.sh` is the `curl … | sh` entry point, and the uv installer it downloads is the only code it runs that is not ours. It is pinned by version **and** SHA-256 and refuses to execute a body that does not match. Review any diff here as a supply-chain change:

1. **Keep the version in the URL.** Astral serves the unversioned `/uv/install.sh` from whatever release is current, so a hash pinned against it breaks for every user on every uv release. Only `/uv/<version>/install.sh` is frozen — flag any change that drops the version from the URL or pins a hash against the unversioned path.
2. **Never a verification bypass.** Flag any environment variable, flag, or code path that skips hash verification — a bypass knob is exactly the hole the pin exists to close. Tests that need their own installer accepted rewrite the constant in a copy of the script instead.
3. **Pin refresh is a release action.** `UV_VERSION` and `UV_INSTALLER_SHA256` change together, via the refresh procedure in `AGENTS.md`, as part of cutting a release — flag a version bump without a matching hash, or vice versa.
4. **Hash mismatch is an incident.** A mismatch against a frozen versioned URL means content changed underneath an immutable release. Flag any handling that retries, warns-and-continues, or auto-refreshes the pin instead of failing hard.
5. **POSIX only.** The script runs under `sh` on fresh machines — flag bashisms.
