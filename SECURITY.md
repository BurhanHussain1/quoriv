# Security Policy

## Supported versions

Quoriv is in pre-release. Until `v1.0.0` ships, security fixes are applied only to the latest commit on `main`.

After `v1.0.0`, the most recent minor version receives security patches for at least 6 months following its release.

| Version | Supported |
|---|---|
| pre-1.0 (main) | ✓ |

---

## Reporting a vulnerability

**Please do not file public GitHub issues for security vulnerabilities.**

If you believe you have found a vulnerability in Quoriv:

1. Email the maintainer at **hussainburhan207@gmail.com** with subject `[SECURITY] Quoriv: <short description>`.
2. Include:
   - A description of the issue
   - Steps to reproduce (or a proof-of-concept)
   - The version / commit you tested against
   - Your assessment of severity and impact
   - Whether you intend to publicly disclose, and on what timeline
3. You will receive an acknowledgement within **72 hours**.

---

## Disclosure timeline

- **Day 0**: Report received, acknowledged.
- **Day 1–7**: Triage, severity assessment, reproduction.
- **Day 7–30**: Fix developed and tested.
- **Day 30–90**: Coordinated disclosure with the reporter.
- **After fix released**: Public disclosure via the changelog and a GitHub Security Advisory.

We aim for faster timelines on critical issues.

---

## What's in scope

- The Quoriv codebase itself (`src/quoriv/`)
- Default configurations shipped with Quoriv
- The permission system
- API key handling
- Plugin loading and MCP server connections

---

## What's out of scope

- Vulnerabilities in upstream dependencies (please report those upstream)
- Vulnerabilities in user-installed plugins or MCP servers
- Issues that require an attacker who already has shell access on the user's machine
- Social engineering of users
- Denial of service against the user's local machine (the user is the operator)

---

## Hall of fame

Security researchers who responsibly disclose verified vulnerabilities will be credited in the release notes and in this file, unless they request anonymity.

*(empty for now)*
