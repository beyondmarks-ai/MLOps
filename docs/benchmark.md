# Public telecom benchmark

The demonstration uses [Maven Telecom Customer Churn](https://mavenanalytics.io/data-playground/telecom-customer-churn), sourced from IBM Cognos Analytics. Maven labels it **Public Domain** and describes a **fictional telecommunications company**. This is a reproducible public benchmark, not evidence of accuracy on an actual customer population.

Download: https://maven-datasets.s3.amazonaws.com/Telecom+Customer+Churn/Telecom+Customer+Churn.zip

Pinned ZIP SHA-256: `c4c64db132d7423abb0a522d60120bbd1d17b3d483eccaaa447561a5e617efba`. A changed checksum fails preparation until the source is reviewed.

## Cohort and cleaning

| Item | Count / treatment |
|---|---|
| Original customers | 7,043 |
| Newly joined customers | 454 excluded from this churn comparison |
| Labeled rows accepted | 6,589: 4,720 Stayed, 1,869 Churned |
| Negative monthly charges | 114 in the selected cohort become missing values; the model learns median imputation from training rows only |
| Duplicate feature records | One repeated record is deduplicated by existing storage rules |
| Stable split sizes | 4,592 train / 940 validation / 1,056 holdout |

Only the predefined churn features are retained. Customer IDs, geography, churn reasons and churn categories never enter the model. `Customer Status` is used solely to define the cohort and target. Missing add-on flags for customers without Internet follow the source dictionary's documented No value.

| Project feature | Benchmark mapping |
|---|---|
| Age, tenure, monthly and total charges | Corresponding source columns |
| Tech support, security, backup, protection | Premium Tech Support, Online Security, Online Backup, Device Protection Plan |
| Partner, dependents, senior | Married; Number of Dependents > 0; Age >= 65 |
| Number of products | Count of Phone Service, Internet Service, Online Security, Online Backup, Device Protection Plan, Premium Tech Support and Unlimited Data subscriptions |
| Contract / payment / Internet | Source categories with spelling normalization; Cable, Bank Withdrawal and Credit Card are supported explicitly |

The source contains a quarter-end snapshot. Metrics measure retrospective classification on this cohort; they do not establish future churn prediction or a time-based validation result. The Married-to-partner and subscription-count mappings are benchmark definitions and must be reviewed before adopting a real customer's schema.

## Training and threshold

The three existing algorithms are tuned with Optuna on the training/validation splits. Each classifier's decision threshold maximizes **validation F1**, with ties resolved toward 0.5. This is an explicit demonstration objective; it is not a learned business cost or a calibrated churn-risk cutoff. The fitted preprocessing, classifier and threshold are serialized together. `/predict` returns the threshold used.

Algorithm selection uses validation AUC among candidates that detect churn. Only then is the candidate evaluated on holdout data. The holdout reports both the chosen threshold and the conventional 0.5 threshold, allowing the precision/recall tradeoff to be inspected without tuning on the holdout. The stable holdout is still reused as a gate on later retraining; a real rollout needs a separate untouched benchmark.

## Reproduction and isolation

```powershell
.venv/Scripts/python.exe -m scripts.prepare_benchmark
```

This writes ignored `data/benchmarks/maven.csv` and its provenance manifest. The download is bounded and verified; no archive paths are extracted to the workstation. The Azure bootstrap script `scripts/seed_benchmark.py` always targets **churn_benchmark** and **MavenChurnModel**. The original **churn** database and **ChurnModel** registry remain separate.

On Azure, initialize the new database with `deploy/init-benchmark.sql`, then run `python -m scripts.seed_benchmark` inside the scheduler container. Switch the deployed `DATABASE_URL` database component to `churn_benchmark` and `MODEL_NAME` to `MavenChurnModel` only after an acceptable benchmark model is registered. Update the local config and Key Vault backup together. The backup script follows the active application database, and its restore checker uses a fresh isolated database.

See [validation](validation.md) for measured results and [operations](azure-operations.md) for on-demand startup and GitHub deployment. Do not combine this benchmark with real customer training rows; use a fresh database for actual customer data.
