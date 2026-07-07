# Whole-document scores vs reference text

Reference: reference.txt (23337 words). Each model's pages concatenated, order-insensitive. token_f1 is the headline.

| model | pages | token_f1 | tok_recall | tok_prec | num_recall | num_halluc | words |
| --- | --- | --- | --- | --- | --- | --- | --- |
| nvidia_NVIDIA-Nemotron-Parse-v1.2 | 46 | 0.881 | 0.838 | 0.928 | 0.896 | 0.247 | 19446 |
| nvidia_NVIDIA-Nemotron-Parse-v1.2__pa | 1 | 0.88 | 0.837 | 0.928 | 0.896 | 0.247 | 18823 |
| baidu_Unlimited-OCR__pa | 1 | 0.83 | 0.835 | 0.826 | 0.896 | 0.591 | 20442 |
| baidu_Unlimited-OCR | 46 | 0.809 | 0.837 | 0.783 | 0.896 | 0.698 | 24437 |
| baidu_Unlimited-OCR__multi__pa | 1 | 0.716 | 0.682 | 0.753 | 0.534 | 0.5 | 18622 |
| baidu_Unlimited-OCR__multi | 1 | 0.092 | 0.048 | 0.853 | 0.0 | 0.0 | 401 |

_num_halluc is inflated: a body-text reference omits numbers that legitimately appear in figures/tables on the page._
