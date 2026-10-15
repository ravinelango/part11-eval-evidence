# Synthetic judge-calibration-kit summaries

**SYNTHETIC.** These files were produced by
[judge-calibration-kit](https://github.com/ravinelango/judge-calibration-kit) with its offline
mock judges on its bundled synthetic datasets:

```bash
jck run   --data examples/synthetic_support_answers.jsonl --judge mock --synthetic --json judge_summary.json
jck ab    --data examples/synthetic_support_answers.jsonl --synthetic --json ab_summary.json
jck agree --data examples/synthetic_two_raters.jsonl --synthetic --json agree_summary.json
```

The numbers describe toy mock judges on 8 to 10 invented examples. They are not a measurement
of any real model or rater.

Turn one into calibration evidence for a requirement:

```bash
p11e build --format jck --results examples/jck_synthetic/ab_summary.json \
           --requirements examples/jck_synthetic/requirements.yaml \
           --requirement-id REQ-JUDGE-001 --min-kappa 0.6 --out out-jck
```

With the default 0.6 threshold, the `ab` summary gives one failing record (`mock`, kappa
0.583) and one passing record (`mock:strict`, kappa 0.800), so REQ-JUDGE-001 shows a deviation.
