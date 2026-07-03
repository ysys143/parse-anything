# OCR sweep - objective scores (axis A)

Ground truth: document.pdf text layer (46 pages). Scan and born scored against the same GT. Higher is better except num_halluc/oracle_flags.

| model | doc | pages | char_sim | token_f1 | num_recall | num_halluc | coverage | oracle_flags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PaddleOCR-VL-pipeline | born | 46 | 0.889 | 0.951 | 0.947 | 0.019 | 1.038 | 57 |
| PaddleOCR-VL-pipeline | scan | 46 | 0.899 | 0.952 | 0.947 | 0.012 | 1.034 | 337 |

## parse-anything contribution (born - scan delta)
| model | d_char_sim | d_token_f1 | d_num_recall |
| --- | --- | --- | --- |
| PaddleOCR-VL-pipeline | -0.01 | -0.001 | 0.0 |

