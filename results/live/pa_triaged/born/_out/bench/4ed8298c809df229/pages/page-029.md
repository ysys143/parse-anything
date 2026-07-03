“Learned” generative model. In BDT, the learned generative model refers to the decision-makerʼs subjective internal model that relates task-relevant variables ( , , and in the left panel of Fig 3D) to external stimuli and behavioral choices ( and , respectively, in the left panel of Fig 3D). As previously known [53,54], the decision-makerʼs internal model is likely to deviate from the “actual” generative model that accurately reflects how the experimenter generated external stimuli due to oneʼs limitations in the sensory and memory apparatus. In the current experimental setup, we assumed that the internal model of the decision-maker deviates from that of the experimenter in the following aspect: Due to the noise in the sensory and memory encoding processes, the decision-maker is likely to believe that many rings of different sizes are presented, although the experimenter used only 5 discrete-size rings. The postexperiment interviews supported this: None of the participants reported perceiving discrete stimuli during the experiment. A deviation like this is known to occur commonly in psychophysical experiments where a discrete number of stimuli were used [40,54,55].

m m′ B S CL

We incorporated the above deviation into the decision-makerʼs internal model by assuming that the stimulus at any given trial is randomly sampled from a Gaussian distribution with mean and variance (as depicted by in Fig 3D):

B σ2S B → S

p(S|B) = N(S;B,σ2S), (3)

σ2S CL

which defines the probability distribution of stimuli conditioned on the class boundary, where corresponds to the extent to which a given decision-maker assumes that stimuli are distributed. Next, the inequality between the class boundary and the stimulus determines the state of the class (as depicted by the converging causal relations involving the class variable, , in Fig 3D):

B → CL ← S CL = large(small) if S > (<)B, (4)

which defines the correct answer of the perceptual task. On the other hand, the sensory measurement

m S σ2m

at any given trial is randomly sampled from a Gaussian distribution with mean and variance (as depicted by in Fig 3D):

p(m|S) = N(m;S,σ2m), (5)

which defines the probability distribution of sensory measurements conditioned on the stimulus, where corresponds to the extent to which the decision-makerʼs sensory system is noisy. Lastly, the mnemonic measurement at any given trial is randomly sampled from a Gaussian distribution with mean and variance (as depicted by in Fig 3D):

m′ m σ2m′ m → m′

p(m′|m) = N(m′;m,σ2m′), (6)

which defines the probability distribution of mnemonic measurements conditioned on the sensory measurement, where corresponds to the extent to which the decision-makerʼs working memory system is noisy. This generative process ( ) is required because the sensory evidence of the stimulus is no longer available in the sensory system—due to a brief (0.3 s;

