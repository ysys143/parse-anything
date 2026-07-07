# Scan (image-only 150dpi) raw model output — token_f1 vs published text (23337 words)

| model | files | token_f1 | tok_recall | tok_prec | num_recall | num_halluc | words |
|---|---|---|---|---|---|---|---|
| nvidia_NVIDIA-Nemotron-Parse-v1.2 | 46 | 0.879 | 0.838 | 0.925 | 0.896 | 0.247 | 19551 |
| baidu_Unlimited-OCR | 46 | 0.810 | 0.840 | 0.783 | 0.896 | 0.686 | 22329 |
| baidu_Unlimited-OCR__multi | 1 | 0.120 | 0.064 | 0.864 | 0.011 | 0.571 | 2586 |

born−scan delta ≈ 0 (Nemotron 0.881→0.879, Unlimited per-page 0.809→0.810). out_scan (parse-anything
scan wrap) was not archived before VM teardown, so only raw_scan is scored.
