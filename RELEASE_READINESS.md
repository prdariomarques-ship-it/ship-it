# Release Readiness — v1.3.0 → v1.3.1 candidate

Prepared 2026-07-18, at the request of the project owner, to evaluate whether
the commits made after the `v1.3.0` GA tag warrant a new patch release. No
tag has been created as part of this document — see "Final recommendation"
for the action awaiting approval.

## 1. Current production state

- **Deployed backend commit**: `2929256182394d8ccd96ec25a1d30f6b170ca912`,
  confirmed live via `GET /api/version` and matching `backend/VERSION.json`
  on the running container (rebuilt and redeployed this session).
- **`v1.3.0` tag**: points at `d64b8be5e2ceb59a3b2c84de2c4cb5d53cab716c` —
  the mobile-sidebar Critical-fix commit, i.e. the GA build. Treated as
  immutable; unchanged by this document.
- **Git HEAD**: `8493a96ecc87d54200b330e2bcac7b5f0cae2bc7`, 3 commits ahead
  of the `v1.3.0` tag, already pushed to `origin/master`.
- **Health**: `database: ok`, `redis: ok`, `qdrant: ok`. `whatsapp: error:
  WhatsAppProviderUnhealthy` — pre-existing, the `openwa` container's
  session isn't authenticated (QR code not scanned); unrelated to this
  deploy and not a regression from it.
- **Tests**: 864/864 backend passing, run against the real repo layout (not
  the environment-truncated container mount used mid-session). Frontend
  untouched this cycle — no rebuild, no retest needed; still whatever was
  last deployed at `v1.3.0`.
- **Working tree**: clean, nothing uncommitted, `master` in sync with
  `origin/master`.

## 2. What changed between `v1.3.0` and current HEAD

Three commits, one of which changes application behavior:

| Commit | Type | Summary |
| --- | --- | --- |
| `2929256` | **fix** | Resolves the two open Medium findings from `RC1_AUDIT.md` |
| `bae59de` | chore | VERSION.json bump recording `d64b8be` as deployed (predates this session; already the parent of the `v1.3.0` tag's own history) |
| `8493a96` | chore | VERSION.json bump recording `2929256` as deployed |

`2929256` is the only commit with runtime effect. It touches 6 backend
files + `docs/api.md`:

- **Deletes** `validate_url` / `validate_file_path` from
  `services/validation.py` — confirmed dead code, no input surface
  anywhere in the backend calls them. No behavior change for any live
  code path (nothing called them).
- **Wires in** `validate_email` / `validate_phone_e164` at
  `agents/tools/domain.py::_add_store_customer` — the one real gap found
  (an LLM-driven tool was writing unvalidated email/phone straight to the
  DB). **Behavior change**: malformed email/phone passed by the agent to
  this tool now raises `ValueError`, which the tool-calling layer already
  converts into a JSON `{"error": ...}` response fed back to the model
  (`agents/tools/base.py::Tool.run`) — not a new failure mode, an existing
  one now reachable for previously-unvalidated input.
- **Adds** `phone` field validation (E.164, `+` optional) to
  `ContactCreate/Update`, `ChurchMemberCreate/Update`,
  `StoreCustomerCreate/Update` in `api/schemas.py`. **Behavior change**:
  `POST`/`PATCH` on `/api/contacts`, `/api/church/members`,
  `/api/store/customers` now reject a `phone` value that isn't
  digits-only (optionally `+`-prefixed), 2–15 digits, no leading zero.
  Verified this does not reject the existing product convention (WhatsApp
  numbers arrive pre-stripped of `+` via `normalize_phone()`, and the
  existing `test_contact_crud` fixture's `"5511999999999"` still passes).
- **Removes** `POST /jobs/{job_id}/cancel` from `jobs/router.py`. **Breaking
  change for direct callers of that specific endpoint only**: it had zero
  callers in the frontend (confirmed) and was a strictly weaker duplicate
  of `POST /admin/jobs/{job_id}/cancel` (no row lock, no audit log, no
  event publish) — the endpoint the dashboard actually uses. `docs/api.md`
  updated to reflect the removal and point at the admin equivalent. Risk:
  if any external script/automation calls `POST /api/jobs/{id}/cancel`
  directly (outside this repo, e.g. a personal curl script), it would now
  get a 405. No such caller was found in this codebase or its docs.

No database migrations, no new dependencies, no frontend changes, no
config/env changes.

## 3. Does this justify v1.3.1?

Yes, under semver-for-a-single-owner-service norms — this is a **patch
release**:

- All changes are bug fixes (dead-code removal, closing a validation gap,
  removing a redundant/lower-safety duplicate endpoint) with no new
  features and no intentional API surface additions.
- The one technically-breaking change (removed `POST /jobs/{id}/cancel`)
  is the reason not to call this a no-op patch, but it's the same
  category of change as removing dead code: the endpoint had no confirmed
  caller anywhere, in this repo or in the docs a caller would have been
  built from. A stricter reading would call this MINOR (public API surface
  shrank); given the single-owner, admin-gated, no-known-caller context and
  that this project's prior patch releases (`v1.1.2`) also included
  behavior changes of comparable scope, PATCH is the pragmatic and
  consistent choice — flagged here explicitly rather than silently decided.
- Test suite is green (864/864), lint is clean, no schema migration risk.

## 4. Remaining blockers

None that block tagging `v1.3.1` specifically. Carried over from
`CURRENT_PROJECT_STATE.md`, unrelated to this patch and not newly
introduced by it:

1. `whatsapp` provider unhealthy (`openwa` session needs QR re-auth) —
   operational, not code; doesn't block a version tag.
2. Optional: parallelize `/api/admin` + `/api/admin/status` (latency,
   0.7–1.0s vs 0.02–0.12s elsewhere) — explicitly optional, not a blocker.
3. `PROJECT_STATUS.md` / `VERSION_HISTORY.md` still describe `v1.3.0-rc1`
   as current — not updated yet for either `v1.3.0` GA or this patch.
   Should be updated as part of whatever commit tags `v1.3.1`, not before.
4. `ROADMAP_v2.md`'s stated v1.3.0 scope (integration reliability) still
   diverges from what actually shipped under that version number — a
   planning-doc reconciliation, not a release blocker.

## 5. Final recommendation

Tag current HEAD (`8493a96`) as **`v1.3.1`**, patch release, once
`PROJECT_STATUS.md` and `VERSION_HISTORY.md` are updated to record it (not
done yet — pending approval to proceed). Suggested tag message:

```
Release v1.3.1

Resolves both open Medium findings from RC1_AUDIT.md:
- services/validation.py: removes 2 dead functions (validate_url,
  validate_file_path — no real input surface), wires the other 2
  (validate_email, validate_phone_e164) into the one real gap found
  (agents/tools/domain.py::_add_store_customer) and into phone fields
  on Contact/ChurchMember/StoreCustomer schemas.
- jobs/router.py: removes POST /jobs/{id}/cancel, an unused duplicate
  of the admin/router.py endpoint the dashboard actually calls, which
  additionally lacked row-locking, audit logging, and event publish.

864/864 backend tests passing. Deployed and verified live via
GET /api/version. No frontend changes, no migrations.
```

No tag created by this document. Waiting for approval to (a) update
`PROJECT_STATUS.md`/`VERSION_HISTORY.md` and (b) create/push `v1.3.1`.
