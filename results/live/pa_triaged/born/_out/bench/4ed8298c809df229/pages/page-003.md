
Competing interests: The authors have declared that no competing interests exist.

Abbreviations: AICc, Akaike information criterion corrected; BADS, Bayesian Adaptive Direct Search; BDT, Bayesian Decision Theory; BMBU, Bayesian model of boundary-updating; DVA, degree in visual angle; IBS, inverse binomial sampling; PDM, perceptual decision-making; PSE, point of subjective equality; RL, reinforcement learning; toi, trial of interest; VDM, value-based decision-making.

Unlike PDM, value-based decision-making (VDM) involves making choices based on decision-makersʼ subjective preferences (e.g., “choosing between two drinks based on their tastes”). Reinforcement learning (RL) algorithms have proven effective in explaining how past rewards affect future VDM based on error-driven incremental mechanisms [12–18]. Intriguingly, there have been attempts to explain the impact of past feedback on subsequent PDM by grafting an RL algorithm onto the PDM processes [3,4,8–10]. This grafting premises that decision-makers treat corrective feedback in PDM similarly to reward feedback in VDM. On this premise, this RL-grafting account proposes that decision-makers update the value of their choice to minimize the difference between the expected reward and the actual reward received, called “reward prediction error” (red dashed arrows in Fig 1A). Importantly, the amount of reward prediction error is inversely related to the strength of sensory evidence—i.e., the extent to which a given sensory measurement of the stimulus supports the choice—because the expected

**Fig 1. Two possible scenarios for what humans learn from feedback for PDM and their distinct predictions of feedback effects.** (A) Decision-making platform for perceptual binary classification. The gray arrows depict how a sensory measurement and feedback are generated from a stimulus , which is sampled from the world, and a choice . The black arrows depict the computational process, where, for a given choice option, a decision-maker computes its expected value by multiplying the probability that the choice is correct given and the class boundary with the value of that choice and make a choice based on . In principle, the decision-maker may update either (red dashed arrows; value-updating) or world (green dashed arrows; world-updating) from . (B) Distinct sensory evidence–dependent feedback effects predicted by the value-updating and worldupdating scenarios. According to the value-updating scenario (left), as sensory evidence becomes stronger, increases, and accordingly, so does . As a result, reward prediction errors become smaller but remain in the direction congruent with feedback, which predicts that feedback effects on subsequent trials diminish asymptotically as a function of the strength of sensory evidence. According to the world-updating scenario (right), as sensory evidence becomes stronger, the stimulus distribution, and accordingly too, becomes shifted farther towards the stimulus in the direction counteracting the influence of feedback. As a result, the direction of feedback effects is the same as that predicted by the value-updating scenario for weak sensory evidence but eventually reverses to the direction incongruent with feedback as sensory evidence becomes stronger.

m F S C

Qoption

poption m B Voption C Qoption Voption

m,C,and F

poption Qoption

Source: https://doi.org/10.1371/journal.pbio.3002373.g001

PLOS Biology | https://doi.org/10.1371/journal.pbio.3002373 November 8, 2023 2 / 32