represent the ways the history factors (feedback and stimulus) exert their contribution to choice bias. In the right panels, , which quantifies the choice bias in the trials following a certain PDM episode at , is plotted as a function of the stimulus size at . The color indicates the direction of choice bias, as in (B) and (C).

PSEtoi+1 toi = [0;large;correct] toi

Source: https://doi.org/10.1371/journal.pbio.3002373.g003

δ = r − Qlarge(small) = r − p(CL = large(small)) × Vlarge(small), α δ r

where , , and are the learning rate, the reward prediction error, and the reward, respectively. The state of feedback determines the value of : for correct; for incorrect. Note that has the statistical decision confidence at the perception stage, i.e., , as one of its 3 arguments. As stressed by the authors who developed this algorithm [9], this feature makes the strength of sensory evidence—i.e., statistical decision confidence—modulate

r r = 1 r = 0 δ p(CL = large(small))

PLOS Biology | https://doi.org/10.1371/journal.pbio.3002373 November 8, 2023 7 / 32

the degree to which the decision-maker updates the chosen value based on feedback (Fig 3E, left). Hence, this belief (confidence)-based modulation of value-updating underlies the stimulus-dependent feedback effects: The amount of feedback effects decreases as sensory evidence becomes stronger since the reward prediction error decreases as a function of , which is proportional to sensory evidence (Fig 3E, right).

p(CL = large (small))

The Bayesian model of boundary-updating (BMBU)

To implement the world-updating scenario, we developed BMBU, which updates the class boundary based on the previous PDM episode in the framework of BDT. Specifically, given “a state of the class variable that is indicated jointly by feedback and choice,” CL, and “a noisy memory recall of the sensory measurement (which will be referred to as ‘mnemonic measurementʼ hereinafter),” , BMBU infers the mean of the size distribution (i.e., class boundary), , by updating its prior belief about , , with the likelihood of , , by inverting its learned generative model of how and CL are generated (Fig 3D, left; Eqs 3–6 in Materials and methods for the detailed formalisms for the learned generative model), as follows:

B B p(B) B p(m′,CL|B) m′

p(B|m′,CL) ∝ p(m′,CL|B)p(B) ≡ p(m′,C,F|B)p(B) :

This inference uses multiple pieces of information from the PDM episode just experienced, including the mnemonic measurement, choice, and feedback, to update the belief about the location of the class boundary (refer to Eqs 8–14 in Materials and methods for more detailed formalisms for the inference). In what follows, we will explain why and how this inference leads to the specific stimulus-dependent feedback effects predicted by the world-updating scenario (Fig 3D, right), where world knowledge is continuously updated.