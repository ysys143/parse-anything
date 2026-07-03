![Fig 2](assets/p10_1.png)

feedback indicating whether the classification was correct or incorrect by the color around the fixation. (C) The 3D state space of the PDM episodes in the experiment. The example episode of toi in (A) is marked by the black cube. (D) Definition of retrospective and prospective history effects. As illustrated in (A) and (C), for any given episode of toi, all the trials labeled with toi−1 and toi+1 are stacked and used to derive the psychometric curves, respectively. The PSEs estimated for the toi−1 and toi+1 psychometric curves quantify the retrospective and prospective history effects, respectively. In this example, the black and gray curves were defined for toi = [0; large; correct] and toi = [0; small; correct], respectively, with circles and bars representing the mean and SEM across 30 participants, respectively. The data underlying this figure (D) can be found in S1 Data. https://doi.org/10.1371/journal.pbio.3002373.g002

and prospective trials quantify the choice biases that exist before and after the PDM episode of interest occurs, respectively, with negative and positive values signifying that choices are biased to large and small, respectively.

Decision-making processes for binary classification

As a first step of evaluating the value-updating and world-updating scenarios, we constructed a common platform of decision-making for binary classification where both scenarios play out. This platform consists of 3 processing stages (Fig 3A). At the stage of “perception,” the decision maker infers the class probabilities, i.e., the probabilities that the ring size (S) is larger and smaller, respectively, than the class boundary (B) given a noisy sensory measurement (m), as follows:

where CL stands for the class variable with the 2 (small and large) states.

At the stage of “valuation,” the decision-maker forms the expected values for the 2 choices ( and ) by multiplying the class probabilities by the learned values of the corresponding choices (

p(CL = large) = p(S > B|m) = ∫

p(CL = small) = 1 − p(CL = large),

Qlarge Qsmall Vlarge Vsmall

and ) as follows:

Qlarge = p(CL = large) × Vlarge; Qsmall = p(CL = small) × Vsmall.