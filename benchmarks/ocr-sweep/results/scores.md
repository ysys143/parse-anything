# OCR sweep - objective scores (axis A)

Ground truth: document.pdf text layer (46 pages). Scan and born scored against the same GT. Higher is better except num_halluc/oracle_flags.

| model | doc | pages | char_sim | token_f1 | num_recall | num_halluc | coverage | oracle_flags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PaddlePaddle_PaddleOCR-VL | born | 46 | 0.859 | 0.938 | 0.94 | 0.012 | 1.531 | 28 |
| PaddlePaddle_PaddleOCR-VL | scan | 46 | 0.864 | 0.956 | 0.962 | 0.012 | 1.444 | 312 |
| allenai_olmOCR-2-7B-1025-FP8 | born | 46 | 0.812 | 0.889 | 0.685 | 0.005 | 1.007 | 32 |
| allenai_olmOCR-2-7B-1025-FP8 | scan | 46 | 0.808 | 0.886 | 0.658 | 0.005 | 1.004 | 261 |
| datalab-to_chandra-ocr-2 | born | 46 | 0.857 | 0.939 | 0.998 | 0.014 | 1.13 | 49 |
| datalab-to_chandra-ocr-2 | scan | 46 | 0.854 | 0.941 | 0.998 | 0.014 | 1.134 | 412 |
| deepseek-ai_DeepSeek-OCR | born | 46 | 0.858 | 0.95 | 0.956 | 0.009 | 1.05 | 25 |
| deepseek-ai_DeepSeek-OCR | scan | 46 | 0.86 | 0.95 | 0.951 | 0.008 | 1.049 | 304 |
| nanonets_Nanonets-OCR2-3B | born | 46 | 0.823 | 0.93 | 0.967 | 0.036 | 1.919 | 25 |
| nanonets_Nanonets-OCR2-3B | scan | 46 | 0.854 | 0.934 | 0.968 | 0.039 | 1.197 | 303 |
| nvidia_NVIDIA-Nemotron-Parse-v1.2 | born | 46 | 0.005 | 0.027 | 0.109 | 0.87 | 2.937 | 626 |
| nvidia_NVIDIA-Nemotron-Parse-v1.2 | scan | 46 | 0.005 | 0.029 | 0.109 | 0.826 | 4.186 | 299 |
| zai-org_GLM-OCR | born | 46 | 0.881 | 0.955 | 0.963 | 0.025 | 1.008 | 25 |
| zai-org_GLM-OCR | scan | 46 | 0.88 | 0.954 | 0.985 | 0.025 | 1.01 | 301 |

## parse-anything contribution (born - scan delta)
| model | d_char_sim | d_token_f1 | d_num_recall |
| --- | --- | --- | --- |
| PaddlePaddle_PaddleOCR-VL | -0.005 | -0.018 | -0.022 |
| allenai_olmOCR-2-7B-1025-FP8 | 0.004 | 0.003 | 0.027 |
| datalab-to_chandra-ocr-2 | 0.003 | -0.002 | 0.0 |
| deepseek-ai_DeepSeek-OCR | -0.002 | 0.0 | 0.005 |
| nanonets_Nanonets-OCR2-3B | -0.031 | -0.004 | -0.001 |
| nvidia_NVIDIA-Nemotron-Parse-v1.2 | 0.0 | -0.002 | 0.0 |
| zai-org_GLM-OCR | 0.001 | 0.001 | -0.022 |

