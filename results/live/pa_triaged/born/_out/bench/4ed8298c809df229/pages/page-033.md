p(Bt|m′t,CLt) ∝ p(m′t,CLt|Bt)p(Bt). (13) t p(Bt−1|m′t−1,CLt−1) Bt

We assumed that, at the beginning of the current trial , the decision-maker recalls the posterior belief

formed (Eq 13) from the previous trial—to use it as the prior of —into the current working memory space, and it is thus subject both to decay and diffusive noise during the recall process. As a result, the prior is basically the recalled posterior, defined as the normal distribution as follows:

λ σdiffusion p(Bt)

N(B^t,σ2B

B^t = λB^postt−1 + (1 − λ)μ0; σ2B

= λσ2t−1post + σ2diffusion, (14)

B^postt−1 σ2t−1post λ = σ

where and denote mean and variance of the previous trialʼs posterior distribution. Note that the decay parameter influences the width and location of the belief distribution and that the diffusive noise of helps to keep the width of the distribution over multiple trials, thus avoiding sharpening and stopping the updating process [60]. In this way, and allow BMBU to address the idiosyncratic choice bias and noise, as we equip the belief-based RL model to do so with and the sofmax rule.

2 0

σ20+σ2t−1post

σdiffusion > 0

λ σdiffusion

μ0

In sum, BMBU posits that human individuals carry out a sequence of binary classification trials with their learned generative model while continually updating their belief about the location of the class boundary in that generative model. BMBU describes these decision-making and boundary-updating processes using a total of 6 parameters ( ), which are set free to account for individual differences.

θ = {μ0,σm,σs,σ0,σm′

,σdiffusion}

PLOS Biology | https://doi.org/10.1371/journal.pbio.3002373 November 8, 2023 23 / 32

PLOS BIOLOGY Corrective feedback on perceptual decisions

Reference models

As the references for evaluating the belief-based RL model and BMBU in predicting the variability of human choices, we created 3 reference models. The “Base” model captures the choice variability that can be explained by the -computation with the class boundary fixed at 0 unanimously for all participants and without any value-updating process. Thus, it has only a single free parameter representing the variability of the sensory measurement ( ). The “Fixed” model captures the choice variability that can be explained by the -computation with the class boundary set free to a fixed constant for each participant and without any value-updating process. Thus, it has 2 free parameters ( ). The “Hybrid” model captures the choice variability that can be explained both by the -computation with the inferred class boundary by BMBU and by the value-updating process implemented by the belief-based RL

θ = {σm} p μ0

θ = {μ0,σm} p