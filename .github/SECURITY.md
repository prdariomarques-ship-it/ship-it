# Security Policy — OSAI

## Supported Versions

The following table describes which versions of OSAI currently receive
security updates:

| Version | Supported |
|---------|-----------|
| v1.5.x (latest) | Yes |
| v1.4.x | Yes (critical only) |
| v1.3.x | No |
| < v1.3 | No |

---

## Reporting a Vulnerability

We take the security of OSAI seriously. If you believe you have found a
security vulnerability, please follow these steps:

### Do NOT

- Open a public issue on GitHub describing the vulnerability.
- Share the vulnerability details in public channels (Discord, Telegram, etc.).

### DO

1. **Email the maintainer directly** at the address listed in the repository
   profile, or use the contact method available via the repository owner's
   GitHub profile page.

2. **Include the following information** in your report:

   - A clear description of the vulnerability.
   - Steps to reproduce (if applicable).
   - The version(s) affected.
   - Potential impact (data exposure, privilege escalation, etc.).
   - A proposed fix or mitigation (if you have one).

3. **Allow time for investigation.** We aim to acknowledge reports within
   48 hours and provide a resolution timeline within 7 days.

### Responsible Disclosure

We follow a responsible disclosure process:

1. You report the vulnerability privately.
2. We investigate and confirm the vulnerability.
3. We develop and test a fix.
4. We release the fix and publicly disclose the vulnerability (with your
   permission) after users have had time to update.

---

## Security Features

### Authentication

- JWT-based authentication with configurable expiration.
- Password hashing via industry-standard algorithms.
- Session management with token rotation.

### Data Isolation

- Multi-tenant data isolation per user/workspace.
- Row-level security enforced at the service layer.
- LLM prompts never receive raw user data without context isolation.

### Dependency Scanning

- Backend dependencies scanned via `pip-audit` in CI.
- Frontend dependencies scanned via `npm audit` in CI.
- Dependabot enabled for automated dependency updates.

### Secrets Management

- All secrets are stored in GitHub Secrets (never in code).
- Environment variables validated at application startup.
- No hardcoded credentials in the codebase.

### Branch Protection

- Direct pushes to `master` are blocked.
- All changes require Pull Request review.
- CI must pass before merge.

---

## Known Limitations

For known security limitations and planned mitigations, see
`TECHNICAL_DEBT.md` and `SECURITY_AUDIT.md` in the repository root.

---

## Acknowledgments

Thank you to everyone who has responsibly disclosed security issues
and helped improve the security posture of OSAI.
