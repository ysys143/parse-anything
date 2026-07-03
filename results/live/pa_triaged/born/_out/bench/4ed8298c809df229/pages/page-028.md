the expected values of the 2 choices and can be obtained by and multiplied with the learned values of the options of small and large, and , respectively. Accordingly, the expected value

QS QL pS pL VS VL QC QS QL

is also defined separately for the choice made between small and large: and .

In the original work, the argmax rule was applied to determine the choice (i.e., the higher determines the choice ). Instead, here, we applied the softmax rule, which selects large with probability

Q C

exp(βQL)

(the higher preferentially selects ) where is an inverse temperature. This feature did not exist in the original model but was introduced here to allow the belief-based RL model to deal with stochastic noise at the decision stage, as we allow the world-updating model (BMBU) to do so.

exp(βQS)+exp(βQL) Q C β

The initial values of small and large choices were set identically as a free parameter . Upon receiving feedback on the decision, the decision-maker updates the value of the selected choice by the reward prediction error with learning rate :

Vinit

VC δ α

VC ← VC + αδ

No temporal discounting is assumed for simplicity. Since the decision-maker treats corrective feedback as rewards (correct: , incorrect: ), the reward prediction error is computed as the deviation of the reward from the expected value:

r = +1 r = 0 δ

δ = r − QC = r − pCVC pC δ δ pC

Note that the belief state (i.e., statistical decision confidence) modulates such that increases as decreases, which is the crucial relationship constraining the belief-based RL modelʼs key prediction on the stimulus-dependent feedback effects. Specifically, upon correct feedback, will take a positive value and reinforce the choice value. However, as increases, the magnitude of such reinforcement will decrease. Critically, despite the decrease of reinforcement as a function of , the sign of reinforcement will never be reversed until the expected value reaches the maximum reward value ( ). Based on the same ground, the sign of reinforcement will never be reversed either in the case of incorrect feedback. The free parameters of the value-updating model are .

δ pC

pC Q r = 1

θ = {μ0,σm,α,β,Vinit}

PLOS BIOLOGY | Corrective feedback on perceptual decisions

World-updating model

As a model of the world-updating scenario, we developed the BMBU. BMBU shares the same platform for PDM with the belief-based RL model (as depicted in Figs 1A and 3A) but, as a BDT model, makes decisions using its “learned” generative model while continually updating its belief about the class boundary , the key latent variable of that internal model (as depicted in the left panel of Fig 3D).
