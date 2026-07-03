Procedure

Stimuli. The stimulus was a thin (.07 degree in visual angle (DVA)), Gaussian-noise fil- tered, black-andwhite ring flickering at 20 Hz on a gray luminance background. On each trial, a fixation first appeared for 0.5 s on average (fixation duration uniformly jittered from 0.3 s to 0.7 s on a trial-to-trial basis) before the onset of a ring stimulus. Five different ring sizes

PLOS Biology | https://doi.org/10.1371/journal.pbio.3002373 November 8, 2023 17 / 32

PLOS BIOLOGY | Corrective feedback on perceptual decisions

(radii of 3.84, 3.92, 4.00, 4.08, 4.16 DVA, denoted by −2, −1, 0, 1, 2, respectively, in the main text) were randomized within every block of 5 trials.

Task. Participants performed a binary classification task on ring size with trial-to-trial corrective feedback. Each individual participated in 5 daily sessions, each consisting of 6 runs, each consisting of 170 trials, ended up performing a total of 5,100 trials. In any given trial, par- ticipants viewed one of the 5 rings and indicated its class (small or large) within 1.2 s after stim- ulus onset by pressing one of the 2 keys using their index and middle fingers. The assignment of computer keys for small and large choices alternated between successive sessions to prevent any unwanted choice bias possibly associated with finger preference. The response period was followed by a feedback period of 0.5 s, during which the color of the fixation mark informed the participants of whether their response was correct (green) or not (red). In case no response had been made within the response period, the fixation mark turned yellow, reminding partic- ipants that a response must be made in time. These late-response trials comprised 0.5418% of the entire trials across participants and were included in data analysis. Meanwhile, the trials on which a response was not made at all comprised 0.0948% of the entire trials. These trials were excluded from analysis and model fitting. As a result, the number of valid trials per participant ranged from 5,073 to 5,100 with an average of 5,095.2 trials. Before each run, we showed par- ticipants the ring stimulus of the median size (4.00 DVA in radius) on the screen for 15 s while instructing them to use that ring as a reference for future trials, i.e., to judge whether a test ring is smaller or larger than this reference ring. This procedure was introduced for the purpose of minimizing any possible carryovers from the belief they formed about the class boundary in the previous session. Participants were encouraged to maximize the fraction of correct trials.

Feedback manipulation. We provided participants with stochastic feedback using a “vir- tual” criterion sampled from a normal distribution . was always fixed at 1.28 throughout the entire runs. In each run, was initially (up to 40 to 50 trials) set to 0 and then to one of the 3 values (

N(μTrue,σTrue) σTrue μTrue

) with the equal proportion (10 runs for each value) for the rest of trials. The stochastic feedback was introduced this particular way to create PDM episodes with (occasional) nonveridical feedback while mimicking a real-world situation where references are slightly noisy and biased in an unnoticeable manner.

μTrue = {−0.4,0,0.4}