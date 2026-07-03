# Whole-document scores vs reference text

Reference: reference.txt (23337 words). Each model's pages concatenated, order-insensitive. token_f1 is the headline.

| model | pages | token_f1 | tok_recall | tok_prec | num_recall | num_halluc | words |
| --- | --- | --- | --- | --- | --- | --- | --- |
| datalab-to_chandra-ocr-2 | 46 | 0.89 | 0.841 | 0.944 | 0.892 | 0.248 | 21152 |
| zai-org_GLM-OCR | 46 | 0.887 | 0.834 | 0.948 | 0.892 | 0.245 | 19449 |
| allenai_olmOCR-2-7B-1025-FP8 | 46 | 0.887 | 0.834 | 0.948 | 0.892 | 0.245 | 19672 |
| PaddleOCR-VL-pipeline | 46 | 0.881 | 0.838 | 0.929 | 0.892 | 0.25 | 19797 |
| deepseek-ai_DeepSeek-OCR | 46 | 0.879 | 0.837 | 0.925 | 0.885 | 0.252 | 20047 |
| PaddlePaddle_PaddleOCR-VL | 46 | 0.876 | 0.832 | 0.926 | 0.871 | 0.255 | 30992 |
| nanonets_Nanonets-OCR2-3B | 46 | 0.875 | 0.84 | 0.913 | 0.892 | 0.248 | 30982 |
| nvidia_NVIDIA-Nemotron-Parse-v1.2 | 46 | 0.066 | 0.035 | 0.704 | 0.022 | 0.854 | 45044 |

_num_halluc is inflated: a body-text reference omits numbers that legitimately appear in figures/tables on the page._
