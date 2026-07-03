PLOS Biology | https://doi.org/10.1371/journal.pbio.3002373 November 8, 2023 20 / 32

PLOS BIOLOGY Corrective feedback on perceptual decisions

Fig 2B) stimulus duration—at the moment of updating the state of the class boundary (as will be shown below in the subsection titled “Boundary-updating”) and instead must be retrieved from the working memory system. The mnemonic recall of the stimulus is known to be noisy, becoming quickly deteriorated right away after stimulus offset, especially for continuous visual evidence such as color and orientation [56,57]. The generative process relating to has been adopted for the same reason by recent studies [58,59], including our group [55], and is consistent with the nonzero levels of memory noise in the modelfit results ( ). The substantial across-individual variability of the fitted levels of is also consistent with the previous studies [55,58,59].

σ2m′ = [1.567, 5.606] σ2m′

With the learned generative model defined above, the decision-maker commits to a deci- sion by inferring the current state of the class variable from the current sensory measure- ment and then updates the current state of the boundary variable from both the current mnemonic measurement and the current feedback .

CL m

m′ F

Decision-making. As for decision-making, BMBU, unlike the belief-based RL model, does not consider the choice values but completely relies on the -computation by selecting the large class if and the small class if . The -computation is carried out by propagating the sensory measurement

p pL > 0.5 pL < 0.5 p

within its learned generative model:

pL = ∫

p(S|m)dS, (7)

where the finite limit of the integral is defined by the inferred state of the boundary , which is continually updated on a trial-to-trial basis (as will be described below). This means that the behavioral choice can vary depending on even for the same value of (as depicted in the “perception” stage of Fig 3A and 3B).

B^ m

Boundary-updating. After having experienced a PDM episode in any given trial , BMBU (i) computes the likelihood of the class boundary by concurrently propagating the mnemonic measurement and the “informed” state of the class variable , which can be informed by feedback and choice in the current PDM episode, within its learned generative model ( ) and then (ii) forms a posterior distribution of the class boundary ( ) by combining that likelihood with its prior belief about the class boundary at the moment ( ), which is inherited from the posterior distribution formed in the previous trial . Intuitively put, as BMBU undergoes successive trials, its poste- rior belief in the previous trial becomes the prior in the current trial, being used as the class boundary for decision-making and then being combined with the likelihood to be updated as the posterior belief in the current trial. Below, we will first describe the computations for (i) and then those for (ii). As

m′t CLt Ft Ct

p(m′t,CLt|Bt) p(Bt|m′t,CLt)

p(Bt) t − 1(p(Bt−1|m′t−1,CLt−1))