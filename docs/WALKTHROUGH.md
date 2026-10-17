# Walkthrough (study guide)

This file grows each phase. Everything here should be something you can explain out loud.

## Design decisions

### One relationship type, `PIVOT`, with a `kind` property
Every attack-relevant edge is `PIVOT`. Variable-length patterns (`-[:PIVOT*1..4]->`) and the
algorithms (`SPpaths`, `pageRank`) take a relationship type, so one type keeps all of them simple.
The `kind` (assume_role, network, ...) says what the hop means.

### Why `depth` is inlined but names are not
FalkorDB rejects a parameter as a variable-length bound, so `*1..$depth` does not work (we tested it
on Cloud). `depth` is validated as an integer from 1 to 8 and written into the query text. This is
safe because only a checked integer can get there. Asset names and ids are always parameters.
Test 6 (injection safety) proves names are treated as data.

### Synthetic seed: a small core plus a large noise region
`app/seed.py` has ~19 hand-written "core" assets where all attack paths live, and ~110 generated
"noise" assets. Noise edges only go noise to noise or core to noise, and crown jewels have no
outgoing edges, so noise adds realism but can never create a path to a crown jewel. That is why the
path count is controlled and the numbers are stable. The generator is seeded (`random.Random(7)`).
The planted traps: a hidden 4-hop route through the forgotten `svc-legacy-etl`; a cheap choke edge
(`role-ci-deployer -> role-prod-admin`, disruption 2); a decoy (`role-prod-admin -> prod-customer-db`,
on the most paths but disruption 9); and a bypass through `jump-host-01` so one fix is not enough.

## Judge questions
(Filled in at Phase 6.)
