chance level (p = 0.2), indicating the probability that a model is favored over others in describing the data by random chance. Bayesian omnibus risk (BOR), the estimated probability that observed differences in model frequencies may be due to chance, is reported (BOR = 1.7636 × 10 ). The data underlying this figure (B, C, D) can be found in S1 Data.

Source: https://doi.org/10.1371/journal.pbio.3002373.g006

PLOS Biology | https://doi.org/10.1371/journal.pbio.3002373 November 8, 2023 12 / 32

PLOS BIOLOGY Corrective feedback on perceptual decisions

unbiased value ( ) and does not update any choice values, thus incorporating neither arbitrary choice preference nor adaptive updating. The “Fixed” model is identical to the Base model except that it incorporates arbitrary choice preference by fitting the constant class boundary to the data. The “Hybrid” model incorporated both value-updating and world- updating algorithms. We quantified the modelsʼ ability to predict human classification choices using log likelihood (Fig 6B) and compared their abilities using the Akaike information crite- rion corrected for sample size (AICc [32]; Fig 6C)). The Fixed modelʼs performance relative to the Base modelʼs (gray dashed lines in Fig 6B and 6C) reflects the fraction of choice variability that is attributed to arbitrary choice prefer- ence. On the other hand, the Hybrid modelʼs performance relative to the Base modelʼs (purple dashed lines in Fig 6B and 6C) reflects the maximum fraction of choice variability that can be potentially explained by either the value-updating model, the world-updating model, or both. Thus, the difference in performance between the Hybrid and Fixed models (the space spanned between the gray and purple dashed lines in Fig 6B and 6C) quantifies the meaningful fraction of choice variability that the 2 competing models of interest are expected to capture. Prior to model evaluation, we confirmed that the 2 competing models (the value-updating and world- updating models) and 2 reference models (the Base and Hybrid models) are empirically distin- guishable by carrying out a model recovery test (S3 Fig).

B = 0

With this target fraction of choice variability to be explained, we evaluated the 2 competing models by comparing them against the Fixed and Hybrid modelsʼ performances while taking into account model complexity with AICc. The value-updating model was moderately better than the Fixed model (paired onetailed t test, , ) and substantially worse than the Hybrid model (paired onetailed t test, , ) and the world-updating model (paired one-tailed t test, , ). By con- trast, the world-updating model was substantially better than the Fixed model (paired one- tailed t test, , ) but not significantly better than the Hybrid model (paired one-tailed t test, , ). These results indicate (i) that the world-updating model is better than the value-updating model in accounting for the choice variability and (ii) that adding the value-updating algorithm to the worldupdating algorithm does not improve the accountability of the choice variability.

t(29) = −2.8540 P = 0.0039 t(29) = 7.6996 P = 8.6170 × 10−9

t(29) = 8.3201 P = 1.7943 × 10−9

t(29) = −10.3069 P = 1.6547 × 10−11 t(29) = −1.0742 P = 0.1458

To complement the above pairwise comparisons, we took the hierarchical Bayesian model selection approach [33–35] using AICc model evidence, to assess how probable it is that each of the 5 models prevails in the population (expected posterior probability; vertical bars in Fig 6D) and how likely it is that