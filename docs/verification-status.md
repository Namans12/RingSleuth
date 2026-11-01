# Verification status — 1 November 2026

## Completed locally

- Frontend dependency audit: zero known findings (previously 19).
- Python 3.12 environment audit: zero known findings; requirements.lock records the resolved dependencies and hashes.
- New traces record actual graph closed-case lookup IDs and vector candidates with their origins. Answers cannot manufacture a retrieval record.
- New batch runs use separate output files and REVIEW-* graph IDs. Historical submission paths and their ancestors are rejected before data loading or service calls.
- Read-back checks the vertex ID and every written field, including its timestamp, rather than accepting a matching verdict alone. A missing graph write/read-back receipt invalidates the new case. Trace-generation failures fail the batch instead of reporting success.
- Ordinary pytest skips live-service tests. The end-to-end service test creates a unique review vertex rather than replacing CASE-HHG-017.

Validation: 150 offline Python tests pass; 30 live tests are skipped. All 119 UI tests, typecheck, lint and build pass. Browser regression checks cover all 120 desktop case tabs and 30 representative tablet tabs.

## Historical submission

All 20 answers and 20 traces pass the current console contract checks: zero errors, six warnings.
The 42 files under cases/ and runs/latest/ have been preserved byte for byte.
The warnings concern graph-lookup citations absent from the original trace retrieval list:

| Case | IDs not independently recorded in its trace retrieval |
| --- | --- |
| HHG-003 | CC-3327, CC-2935 |
| HHG-004 | CC-3778, CC-1736 |
| HHG-010 | CC-0873 |
| HHG-012 | CC-0003 |
| HHG-015 | CC-3886, CC-0615 |
| HHG-018 | CC-0631 |

An answer citation or graph visualization constructed from that answer is not independent
proof of retrieval. A source CSV check or live lookup can provide a new dated corroboration;
it cannot establish exactly what the original unlogged lookup returned. Do not backfill old
traces or suppress these warnings. A clean new run must have its own provenance and results.

## Still required before calling the live project verified

1. Locate the RingSleuth .env file and all four supplied CSVs: transactions.csv, identity.csv,
   closed_cases_history.csv and case_pack.csv. Neither credentials nor datasets are included
   in this checkout. Share paths only, never credential values.
2. Check service access, embedding model availability, query results and source membership
   for the disputed closed cases. Record timestamps, inputs and receipts separately.
3. Verify a representative new investigation, graph write/read-back and UI trace in a review
   workspace. Then run the full new batch as appropriate and inspect its validation results.
4. Inspect remaining semantic limits rather than declaring all verdicts correct: the answer
   key is unavailable; six submitted verdicts are uncertain; some submitted patterns are
   inconsistent with verdict labels. Customer replies are simulated, not actual outreach.

## Public demo direction

The deliverables checklist in docs/superpowers/specs/2026-09-22-tigergraph-fraud-agent-design.md
requires a 3–5 minute demo. Target about four minutes after live verification: the problem,
a graph-backed investigation, recorded evidence requests and action changes, human approval
routes, case memory and SAR drafting, followed by measured results and limitations.
Use Remotion for the animated presentation, with clear recorded-replay labels. Show SARs as
drafts and recommendations as recommendations. Do not invent accuracy, successful filings,
live customer contact or a live service connection. The static console reads saved JSON.
YouTube publication and adding its final link follow owner review of the rendered video.
Résumé and the portfolio hero video remain deferred. Scam Shield is outside this work.
