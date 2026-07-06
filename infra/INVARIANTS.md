# Deploy invariants

Invariants that MUST hold for `make deploy-infra` and friends to be
safe / non-surprising. Each has a corresponding test in tests/unit/.

## INV-001: BQ_LOCATION follows REGION by default

If the operator explicitly sets `REGION` (either on the make command
line or in `.env`) but does not explicitly set `BQ_LOCATION`,
`BQ_LOCATION` MUST resolve to `REGION`. `.env.example` MUST NOT ship
a hardcoded `BQ_LOCATION=US` default, because that value survives a
`cp .env.example .env` and silently mismatches any non-us REGION the
operator later picks.

**Violation shape**: operator runs `make deploy-infra REGION=asia-southeast1`
after `make install` created their `.env` from the template. Preflight
correctly refuses because `.env` still has `BQ_LOCATION=US`. Operator
did nothing wrong; the template default betrayed them.

**Correct behavior**: `.env.example`'s BQ_LOCATION line is commented
out (or absent) so new users inherit the REGION-derived default from
Makefile. Explicit multi-region ("US" / "EU" / "asia") stays available
as an explicit opt-in for advanced users.

**Rationale**: Data-residency intent (data in region X, compute in
region Y) is a legitimate but rare configuration. Making it the
DEFAULT behavior surprises 90%+ of deployers. The default should
be "everything co-located". Advanced users can opt into
cross-region by setting BQ_LOCATION explicitly.
