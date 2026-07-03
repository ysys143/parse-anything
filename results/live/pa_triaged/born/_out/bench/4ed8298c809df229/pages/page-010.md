Lastly, at the stage of “decision,” the decision-maker commits to the choice whose expected value is greater than the other. In this platform, choice bias may originate from the perception or valuation stage. Suppose the decision-makerʼs belief about size distribution at the perception stage is not fixed but changes depending on previous PDM episodes (Fig 3B, top). Such changes lead to the changes in PSE of the psychometric curve because the class probabilities change as the class boundary changes (Fig 3B, bottom). Alternatively, suppose the decision makerʼs learned values of the choices are not fixed but change similarly (Fig 3C, top). These changes also lead to the changes in PSE of the psychometric curve because the expected values change as the choice values change (Fig 3C, bottom).

The belief-based RL model

To implement the value-updating scenario, we adapted the belief-based RL model [9] to the current experimental setup. Here, feedback acts like a reward by positively or negatively reinforcing the value of choice ( ) with the deviation of the reward outcome (r) from the expected value of that choice (

Vlarge(small) Qlarge(small)

), as follows:

Vlarge(small) ← Vlarge(small) + αδ;

PLOS Biology | https://doi.org/10.1371/journal.pbio.3002373 November 8, 2023 6 / 32