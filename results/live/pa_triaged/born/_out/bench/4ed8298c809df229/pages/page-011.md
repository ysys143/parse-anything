![Fig 3](assets/p12_1.png)

PLOS BIOLOGY | Corrective feedback on perceptual decisions

**Fig 3. Implementation of the value-updating and world-updating scenarios into computational models in a common PDM platform.** (A) Computational elements along the 3 stages of PDM for binary classification. At the “perception” stage, the probabilities that the class variable takes its binary states small and large— and —are computed by comparing the belief on the stimulus size against the belief on the class boundary —the mean of the belief on stimulus distribution in the world . At the “valuation” stage, the outcomes of the perception stage are multiplied by the learned values to produce the expected values . At the “decision” stage, the choice with the greater expected value is selected. (B, C) Illustration of 2 potential origins of choice biases, one at the “perception” stage (B) and the other at the “valuation” stage (C). The color indicates the direction of choice bias (yellow for bias to large; black for no bias; blue for bias to small). (D, E) Illustration of the architectures (left panels) and predictions on the stimulus-dependent feedback effects (right panels) of BMBU (D) and the belief-based RL model (E). In the left panels, the dashed arrows

p(CL = large) p(CL = small) p(S|m) B p(S)

Vs Qs