# parse-anything OCR model sweep - comparison report

Models: 5 | docs: born-digital (grounded) + scanned (raw-OCR stress)

## Status & timing
| model | doc | status | pages | done | fail | avg_lat_s | total_s | avg_chars |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| allenai_olmOCR-2-7B-1025-FP8 | born | ok | 47 | 46 | 0 | 52.1 | 2398.5 | 2663 |
| allenai_olmOCR-2-7B-1025-FP8 | scan | ok | 47 | 46 | 0 | 49.1 | 2258.3 | 2645 |
| datalab-to_chandra-ocr-2 | born | ok | 47 | 46 | 0 | 62.5 | 2876.3 | 3644 |
| datalab-to_chandra-ocr-2 | scan | ok | 47 | 46 | 0 | 61.4 | 2826.4 | 3637 |
| deepseek-ai_DeepSeek-OCR | born | ok | 47 | 46 | 0 | 20.7 | 951.6 | 3089 |
| deepseek-ai_DeepSeek-OCR | scan | ok | 47 | 46 | 0 | 20.0 | 919.6 | 3080 |
| nanonets_Nanonets-OCR2-3B | born | ok | 47 | 46 | 0 | 55.5 | 2551.3 | 4131 |
| nanonets_Nanonets-OCR2-3B | scan | ok | 47 | 46 | 0 | 41.4 | 1902.1 | 2935 |
| zai-org_GLM-OCR | born | ok | 47 | 46 | 0 | 21.6 | 992.5 | 2574 |
| zai-org_GLM-OCR | scan | ok | 47 | 46 | 0 | 21.3 | 979.6 | 2578 |

## parse-anything artifact stats (product view)
| model | doc | pages | md_chars | oracle_flags | nodes | sections | zones |
| --- | --- | --- | --- | --- | --- | --- | --- |
| allenai_olmOCR-2-7B-1025-FP8 | born | 46 | 122507 | 32 | 578 | 33 | 4 |
| allenai_olmOCR-2-7B-1025-FP8 | scan | 46 | 121685 | 261 | 56 | 0 | 1 |
| datalab-to_chandra-ocr-2 | born | 46 | 167655 | 49 | 574 | 33 | 4 |
| datalab-to_chandra-ocr-2 | scan | 46 | 167345 | 412 | 46 | 0 | 1 |
| deepseek-ai_DeepSeek-OCR | born | 46 | 142138 | 25 | 578 | 33 | 4 |
| deepseek-ai_DeepSeek-OCR | scan | 46 | 141718 | 304 | 55 | 0 | 1 |
| nanonets_Nanonets-OCR2-3B | born | 46 | 190028 | 25 | 608 | 33 | 4 |
| nanonets_Nanonets-OCR2-3B | scan | 46 | 135050 | 303 | 85 | 0 | 1 |
| zai-org_GLM-OCR | born | 46 | 118416 | 25 | 607 | 33 | 4 |
| zai-org_GLM-OCR | scan | 46 | 118633 | 301 | 84 | 0 | 1 |

## Raw transcription excerpt - page 1 (scanned doc)
The scanned doc has no text layer, so this is each model's unaided OCR.

### allenai_olmOCR-2-7B-1025-FP8
```
---
primary_language: en
is_rotation_valid: True
rotation_correction: 0
is_table: False
is_diagram: False
---
Corrective feedback guides human perceptual decision-making by informing about the world state rather than rewarding its choice

Hyang-Jung Lee1, Heeseung Lee1, Chae Young Lim2, Issac Rhim3, Sang-Hun Lee1*

1 Department of Brain and Cognitive Sciences, Seoul National University, Seoul, South Korea, 2 Department of Statistics, Seoul National University, Seoul, South Korea, 3 Institute of Neuroscience, University of Oregon, Eugene, Oregon, United States of America

visionsl@snu.ac.kr

Abstract

Corrective feedback received on perceptual decisions is crucial for adjusting decision-making strategies to improve future choices. However, its complex interaction with other decision compone
```

### datalab-to_chandra-ocr-2
```
<div data-bbox="269 42 727 70" data-label="Page-Header"><h1>CorrectiveFeedbackCSNL</h1></div><div data-bbox="79 152 470 189" data-label="Page-Header"><h2>PLOS BIOLOGY</h2></div><div data-bbox="72 217 131 235" data-label="Text"><p>figure</p></div><div data-bbox="25 257 214 273" data-label="Text"><p>RESEARCH ARTICLE</p></div><div data-bbox="23 322 924 445" data-label="Section-Header"><h1>Corrective feedback guides human perceptual decision-making by informing about the world state rather than rewarding its choice</h1></div><div data-bbox="23 479 770 500" data-label="Text"><p>Hyang-Jung Lee<sup>1</sup>, Heeseung Lee<sup>1</sup>, Chae Young Lim<sup>2</sup>, Issac Rhim<sup>3</sup>, Sang-Hun Lee<sup>1*</sup></p></div><div data-bbox="23 520 870 540" data-label="Text"><p><sup>1</sup> Department of
```

### deepseek-ai_DeepSeek-OCR
```
<|ref|>title<|/ref|><|det|>[[70, 150, 468, 192]]<|/det|>
# PLOS BIOLOGY  

<|ref|>text<|/ref|><|det|>[[75, 217, 130, 235]]<|/det|>
figure  

<|ref|>text<|/ref|><|det|>[[27, 257, 213, 275]]<|/det|>
RESEARCH ARTICLE  

<|ref|>title<|/ref|><|det|>[[25, 323, 925, 448]]<|/det|>
# Corrective feedback guides human perceptual decision-making by informing about the world state rather than rewarding its choice  

<|ref|>text<|/ref|><|det|>[[30, 480, 768, 502]]<|/det|>
Hyang- Jung Lee1, Heeseung Lee1, Chae Young Lim2, Issac Rhim3, Sang- Hun Lee1\*  

<|ref|>text<|/ref|><|det|>[[27, 520, 914, 590]]<|/det|>
1 Department of Brain and Cognitive Sciences, Seoul National University, Seoul, South Korea, 2 Department of Statistics, Seoul National University, Seoul, South Korea, 3 Institute of Neuroscience, U
```

### nanonets_Nanonets-OCR2-3B
```
CorrectiveFeedbackCSNL

PLOS BIOLOGY
figure
RESEARCH ARTICLE

Corrective feedback guides human perceptual decision-making by informing about the world state rather than rewarding its choice

Hyang-Jung Lee1, Heeseung Lee1, Chae Young Lim2, Issac Rhim3, Sang-Hun Lee1*
1 Department of Brain and Cognitive Sciences, Seoul National University, Seoul, South Korea, 2 Department of Statistics, Seoul National University, Seoul, South Korea, 3 Institute of Neuroscience, University of Oregon, Eugene, Oregon, United States of America
* visionsl@snu.ac.kr

Abstract
Corrective feedback received on perceptual decisions is crucial for adjusting decision-making strategies to improve future choices. However, its complex interaction with other decision components, such as previous stimuli and choices, challe
```

### zai-org_GLM-OCR
```
Corrective feedback guides human perceptual decision-making by informing about the world state rather than rewarding its choice

Hyang-Jung Lee1, Heeseung Lee1, Chae Young Lim2, Issac Rhim3, Sang-Hun Lee1*

1 Department of Brain and Cognitive Sciences, Seoul National University, Seoul, South Korea, 2 Department of Statistics, Seoul National University, Seoul, South Korea, 3 Institute of Neuroscience, University of Oregon, Eugene, Oregon, United States of America

• visionsl@snu.ac.kr

Abstract

Corrective feedback received on perceptual decisions is crucial for adjusting decision-making strategies to improve future choices. However, its complex interaction with other decision components, such as previous stimuli and choices, challenges a principled account of how it shapes subsequent decis
```

