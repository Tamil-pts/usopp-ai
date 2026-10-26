# Local WorkHub performance benchmark

Before: 4.86.0 / After: 4.87.0.

Synthetic fixture: 150 documents, 400 jobs, one 40-page searchable PDF. Forty local router requests at each concurrency; six extraction calls (one cold, five repeats). Same Windows checkout and Python environment. Fixture accounts replace authentication for route measurements; password verification, HTTP transport, reverse proxy, Docker, GPU/model inference and production company data are excluded.

| Concurrent requests | Median before / after (ms) | p95 before / after (ms) | Requests/s before / after |
| ---: | ---: | ---: | ---: |
| 1 | 96.2 / 20.4 | 137.0 / 24.3 | 9.99 / 48.72 |
| 4 | 295.6 / 141.6 | 331.3 / 156.9 | 13.44 / 28.46 |
| 8 | 681.5 / 353.3 | 789.2 / 461.6 | 11.57 / 21.63 |

| Document processing | Before | After |
| --- | ---: | ---: |
| First 40-page extraction | 2865.7 ms | 3574.8 ms |
| Repeat extraction median | 1596.7 ms | 9.6 ms |
| Extraction Python allocation peak | 8.86 MiB | 8.09 MiB |
| Benchmark process peak RSS | 97.84 MiB | 98.96 MiB |

Repeat extraction latency fell 99.40%. First extraction increased 24.7% while writing integrity-checked, reusable file/page outputs. Extracted text hashes and source page counts match. Peak RSS was effectively unchanged; these measurements do not demonstrate a production memory reduction.

Both isolated databases passed SQLite integrity checking. This is a small local comparison, not a Linux capacity guarantee or a real Qwen, Whisper, OCR or concurrent editing benchmark. Re-run under the target server limits and representative company documents before selecting larger worker budgets.

Reproduce: `python scripts/perf/workhub_benchmark.py --output .build/workhub-performance/after.json`. Raw before/after measurements and build/test logs are in `.build/workhub-performance/`. The before measurement was taken before queue/cache changes.
