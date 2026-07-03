Data analysis

For any given PDM episode at a toi, we quantified the retrospective and prospective history effects by probing the psychometric curves at the trials before and after toi, respectively. The psychometric function ( ) was estimated by fitting the cumulative Gaussian distribution ( ) to the curves using Psignifit package [50–52] (https://github.com/wichmann-lab/psignifit), as follows:

ψ(x) F

ψ(x;μ,σ) = F(x;μ,σ), μ σ F μ

where and are the mean and standard deviation of . By finding the best-fitting value of , we defined the PSE (the stimulus level with equal probability for a small or large choice), which was used as the summary statistics that quantifies the history effects associated with a given PDM episode. To ensure reliable PSE estimates, we acquired bootstrap samples ( ) of psychometric curves based on the binomial random process and took their aver- age as the final estimate for each PDM episode. In our main data analysis, the results of which are displayed in Fig 7, we chose not to include the parameters for guess or lapse rates in esti- mating PSEs. This was done to prevent unfair overfitting problems from occurring in infre- quent episode types with small numbers of trials available for fitting. On the other hand, to preclude any potential confounding problem related to the task difficulty associated with PDM

N = 5,000

PLOS Biology | https://doi.org/10.1371/journal.pbio.3002373 November 8, 2023 18 / 32

episode types, we also repeated the above PSE estimation procedure with guess ( ) and lapse ( ) rates included as free parameters: . The results did not differ between the original estimation procedure without the lapse and guess rates and the procedure with the lapse and guess rates (Bonferroni-corrected P = 0.2023 ~ 1.000; paired two-tailed t tests; see S2 Data for detailed statistical information).

γ λ ψ(x;μ,σ,γ,λ) = γ + (1 − γ − λ)F(x;μ,σ)

Value-updating model

As a model of the value-updating scenario, we used the belief-based RL model proposed in the previous work [9,10]. This model incorporates RL algorithm into the conventional Bayesian formalism of decision confidence—also known as statistical decision confidence using a partially observable Markov decision process (Fig 3E). In this model, the decision-maker, given sensory measurement , computes the probability that the stimulus belongs to “large” ( ) or “small” ( ) class (hereinafter the pcomputation), where . This probability will be referred to as a “belief-state,” as in the original work [9,10]. Here, the probability distribution is defined as a normal distribution with mean and standard deviation . Whereas was assumed to be zero in the original work, we set free as a constant parameter to allow the belief-based RL model to deal with any potential individualsʼ idiosyncratic choice bias, as we will allow the world-updating model (BMBU) to do so (see below). Next,

m pL pS = 1 − pL

pL = ∫μ∞

p(S|m) m σm μ0 μ0