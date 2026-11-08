# Deployment validation — 2026-11-08

Application: https://churn-mlops-617db570.centralindia.cloudapp.azure.com

## Current benchmark and GitHub deployment

The active model is **MavenChurnModel version 1**, Gradient Boosting, using the public fictional telecom benchmark in its own MySQL database. [Benchmark provenance and metrics](benchmark.md) documents mappings, exclusions and threshold tradeoffs. The old synthetic database still contains 3,000 samples; the benchmark contains 6,588 unique samples. Twelve live HTTPS predictions and feedback submissions passed, including the exact class-versus-stored-threshold check. Fresh MySQL and PostgreSQL backups were uploaded at 08:03 UTC; the benchmark MySQL backup was downloaded and restored into an isolated database with all 6,588 samples. The active configuration backup in Key Vault was updated. PostgreSQL restore remains untested.

The benchmark commit passed **105 tests with 88.05% coverage on GitHub Linux**, plus lint and both Docker image builds: [CI run](https://github.com/beyondmarks-ai/MLOps/actions/runs/42460216245). Local Windows tests also passed (105 tests, 88.03% coverage).

OIDC authentication and actual deployment were verified through GitHub: [initial deployment](https://github.com/beyondmarks-ai/MLOps/actions/runs/42459464726) and [benchmark code deployment](https://github.com/beyondmarks-ai/MLOps/actions/runs/42460216346). Both checked the exact commit, both API instances and public HTTPS, then returned an initially stopped VM to deallocated state. The initial OIDC subject mismatch was corrected using GitHub's actual subject, including immutable owner/repository IDs. No stored client secret or SSH key is used by GitHub.

A final [redeployment](https://github.com/beyondmarks-ai/MLOps/actions/runs/42461273303) verified commit `4bb586c1bd4757627193088fa86ee447573835c9`, both Maven model API instances, public HTTPS, and the already-running VM case. The VM was subsequently deallocated to save compute credits.

The sections below preserve earlier deployment evidence; their model-3 synthetic metrics are historical, not the active benchmark results.

## On-demand control follow-up

The Windows [launcher](../Backend-Control.cmd) was added after the original deployment validation. Five focused tests passed for readiness polling, deallocation, timeouts, error propagation, action validation and fixed Azure resource scope. A Tkinter smoke check verified window creation, four button bindings and asynchronous completion. The window opened successfully; visual inspection was denied because Computer Use was not approved to access `pythonw`.

A real stop/start cycle used the same control functions as the buttons. Azure confirmed deallocation, then both API containers recovered automatically on start with Production model 3. The 3,000-row dataset remained present and a new HTTPS prediction succeeded. Backups were taken before the cycle. The VM was deallocated again after validation to save compute credits; use Start in the launcher before opening the web app. This state is a point-in-time record, not a live status indicator.

## Automated checks

- Linux runtime image: **90 tests passed**, **88.67% statement coverage**, exceeding the 80% gate (67 seconds).
- Ruff check and format check passed for `src`, `dags`, `tests`, and `scripts`.
- Both Docker images install dependencies with `pip check`.
- Airflow reports no DAG import errors.
- `git diff --check` passed; no runtime secret values found in tracked/non-ignored text files.
- Dashboard JavaScript syntax passed `node --check`; HTTPS HTML response succeeded. Visual browser testing was blocked by computer-use access and is not claimed.

Tests include real MLflow training/artifact round trips, upload/predict/feedback integration, rejected candidates, drift, source adapters, validation, authorization, dataset deduplication, stable splits, concurrent queue claims, and retry exhaustion after failure or worker loss. Test runs use isolated storage and no production credentials.

## Live model and API

An explicitly synthetic dataset with 3,000 rows bootstrapped the system. Airflow trained and tuned all three algorithms. Version 3 (Logistic Regression) passed the nonzero-recall recovery rule and replaced version 1. Both API containers independently returned healthy status with Production version 3 after deployment.

| Synthetic holdout metric | Model 3 |
|---|---:|
| ROC-AUC | 0.737995 |
| Accuracy | 0.671024 |
| Precision | 0.124224 |
| Recall | 0.666667 |
| F1 | 0.209424 |

These are demonstration results, not estimates for a real customer population. The previous classifier had high accuracy but zero recall; balanced class weights improve detection at the cost of false positives. Precision remains low. A business decision threshold and representative data are required before operational use.

| HTTPS scenario | Predictions | Feedback | Concurrency | Client p50 | Client p95 |
|---|---:|---:|---:|---:|---:|
| Synthetic prediction/feedback | 50 | 50 actual synthetic labels | 4 | 173.60 ms | 201.60 ms |
| Deliberately shifted synthetic features | 100 | None | 4 | 174.49 ms | 204.14 ms |

All requests completed successfully. The script also checked unauthenticated prediction rejection (401), prediction-key denial of administrator retraining (403), and bounded prediction probabilities. Latency includes the workstation-to-Azure HTTPS network path. This is a small smoke/load check, not a sustained capacity benchmark.

## Closed-loop evidence

Airflow monitoring at 05:26 UTC processed 150 predictions for model 3, including 50 labeled observations. It detected feature drift and performance degradation (window AUC 0.553191 versus holdout 0.737995), then inserted durable request `monitor-3-83060` with reason `performance_drop`. This small labeled window is statistically noisy; it demonstrates the mechanism, not a confident real-world degradation finding. The 100 shifted rows were deliberately left unlabeled and cannot become training truth.

The normal five-minute Airflow schedule picked up this request at 05:30 UTC and completed it at 05:30:19, in one attempt. Candidate version 4 was rejected by the improvement gate; serving remained healthy on version 3. This verifies the deployed monitor ? durable request ? scheduled training ? evaluation ? retain-champion loop. Rejected candidates remain registered for inspection. Retraining on unchanged labeled data does not guarantee an improvement.

## Persistence and recovery

- MySQL and PostgreSQL dumps uploaded to private Azure Blob Storage using VM managed identity.
- Latest MySQL backup downloaded from Blob Storage and restored into a fresh isolated database; 3,000 training samples verified, test database removed, live database untouched.
- Daily 02:15 UTC backup cron installed; 14-day backup lifecycle retention and 7-day Blob soft delete enabled.
- Runtime configuration backup exists as enabled Key Vault secret `runtime-config`.
- PostgreSQL restore, full VM-loss recovery and region failover have not been tested.

## Remaining limits

One VM hosts serving, orchestration and databases; maintenance/redeployment can interrupt service. No distributed dataset processing, cross-VM availability, sustained-load guarantee, real-data accuracy guarantee or penetration test is claimed. Both test and synthetic data are clearly separated from claims about customer outcomes. Start a separate database before onboarding real customer training data.

GitHub origin permissions are read-only for the active account. Workflow files are prepared locally, but were not pushed or activated upstream. The Azure CLI/SSH deployment path was exercised successfully. [Operations](azure-operations.md) includes access, backup and stop/start commands; [coverage](report02-current-coverage.md) maps the remaining report gaps.
