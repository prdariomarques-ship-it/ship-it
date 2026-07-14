# DARIO OS v1.0.0-LTS — LONG-TERM SUPPORT POLICY

**Release Date:** July 14, 2026  
**Support Period:** 3 Years (until July 14, 2029)  
**Freeze Date:** July 14, 2026  
**Status:** ACTIVE

---

## SUPPORT COMMITMENT

Dario OS v1.0.0-LTS receives **Long-Term Support (LTS)** guaranteeing:

✅ **Security Patches** — Deployed within 48-72 hours of advisory  
✅ **Critical Bug Fixes** — Deployed within 1 week of discovery  
✅ **Stability Guarantee** — No breaking changes to API or runtime  
✅ **Compatibility Assurance** — No forced upgrades to dependencies  

---

## PERMITTED CHANGES IN LTS PERIOD

### ✅ ALLOWED

1. **Security Patches**
   - CVE fixes
   - Dependency security updates
   - Protocol hardening

2. **Critical Bug Fixes**
   - Production outages
   - Data corruption risks
   - Authorization bypasses

3. **Compatibility Fixes**
   - OS/platform updates required
   - Dependency incompatibilities
   - Required by future modules

4. **Documentation Updates**
   - Operational procedures
   - Configuration guides
   - Troubleshooting steps

### ❌ PROHIBITED

1. **New Features**
   - No API additions
   - No new endpoints
   - No new pages

2. **Architectural Changes**
   - No database schema redesigns
   - No storage system changes
   - No communication protocol changes

3. **Dependency Upgrades**
   - No major version bumps
   - No breaking minor versions
   - Only patch versions for security

4. **Refactoring**
   - No code restructuring
   - No module reorganization
   - No pattern changes

5. **Performance Optimizations**
   - No speculative improvements
   - Only fixes for actual bottlenecks

---

## SUPPORT MATRIX

| Component | Support | Notes |
|-----------|---------|-------|
| **Frontend** | 3 years | Next.js 14.2.x only |
| **Backend** | 3 years | FastAPI 0.115+ |
| **Runtime** | 3 years | DRT v1.0.0 |
| **Database** | 3 years | Postgres 13+ / SQLite |
| **Python** | 3 years | 3.11+ |
| **Node.js** | 3 years | 20+ LTS |

---

## PATCH RELEASE SCHEDULE

### Security Patches
- **Frequency:** As-needed (within 48-72 hours of disclosure)
- **Versioning:** v1.0.X (patch increment)
- **Example:** v1.0.1, v1.0.2, v1.0.3

### Maintenance Updates
- **Frequency:** Monthly (if patches available)
- **Batch Policy:** Up to 5 patches per month
- **Review:** Security advisory + compatibility test

### End-of-Life
- **Date:** July 14, 2029
- **Final Patch:** v1.0.999 (theoretical maximum)
- **Support Ends:** No patches after EOL date

---

## VULNERABILITY RESPONSE SLA

### Critical (CVSS 9.0-10.0)
- **Discovery:** Immediate internal notification
- **Assessment:** 2-4 hours
- **Patch Development:** 4-8 hours
- **Testing:** 8-12 hours
- **Deployment:** 24 hours maximum
- **Communication:** Public disclosure + fix

### High (CVSS 7.0-8.9)
- **Assessment:** Within 24 hours
- **Patch Development:** 24-48 hours
- **Testing:** 48 hours
- **Deployment:** 72 hours maximum

### Medium (CVSS 4.0-6.9)
- **Assessment:** Within 1 week
- **Patch Development:** 1 week
- **Batch with other updates:** Monthly cycle

### Low (CVSS 0.1-3.9)
- **Review:** Quarterly assessment
- **Batch deployment:** Annual major update

---

## KNOWN VULNERABILITIES ACCEPTED IN LTS

### Next.js v14.2.21 — 5 Known Vulnerabilities

| Vulnerability | CVE | Severity | Status | Mitigation |
|---------------|-----|----------|--------|-----------|
| Image Optimization Cache Key Confusion | GHSA-g5qg-72qw-gw5v | HIGH | MITIGATED | Feature disabled |
| Middleware SSRF | GHSA-4342-x723-ch2f | HIGH | MITIGATED | Limited usage |
| Server Components DoS | GHSA-5j59-xgg2-r9c4 | HIGH | MITIGATED | Feature not used |
| Dev Server Info Exposure | GHSA-3h52-269p-cp9r | CRITICAL | MITIGATED | Production only |
| Image Optimizer Storage | GHSA-3x4c-7xq6-9pq8 | MODERATE | MITIGATED | Feature disabled |

**Rationale:** Vulnerabilities affect unused features. Upgrade path requires major version change with new vulnerabilities and breaking changes. Cost > Benefit.

**Monitoring:** These CVEs added to quarterly security review. If new exploits discovered, immediate major version upgrade planned.

---

## MODULE COMPATIBILITY GUARANTEE

Future modules built on Dario OS v1.0.0-LTS platform must:

- ✅ Consume platform services (do not modify core)
- ✅ Implement backward compatibility (API versioning)
- ✅ Pass integration tests with LTS runtime
- ✅ Not require platform dependency upgrades
- ✅ Document breaking changes in module release notes

---

## SUPPORT CONTACTS

**Security Issues:** security@darioos.com  
**Bug Reports:** issues@darioos.com  
**Feature Requests:** roadmap@darioos.com (deferred to v2.0)  
**Operational Support:** ops@darioos.com

---

## TERMS

This LTS support agreement is binding from release date through EOL date. No support provided after July 14, 2029. Upgrade to next major version required for continued support beyond LTS period.

