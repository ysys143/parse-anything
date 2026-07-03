model. Thus, it has 9 free parameters ( ). In Fig 6B–6D, the differential goodness of fit measures on the y-axis indicate the subtractions of the performance of the “Base” model from those of the remaining models.

θ = {μ0,σm,σs,σ0,σm0,σdiffusion,α,β,Vinit}

Model fitting

For each participant, we fitted the models to human choices over N valid trials ( ) of M (= 10) experimental runs under K (= 3) conditions, where invalid trials were the trials in which the participants did not make any response. For any given model, we denote the log likelihood of a set of parameters given the data as follows:

θ

Kcond

Mruns

Ntrials

LL(θ,model) = logp(data|θ,model) =

logp(Ci,j,k|θ,model),

k=1

j=1

i=1

where denotes the participantʼs choice (large or small) on the i-th trial of the j-th run under the j-th condition. Computation of this is analytically intractable given the stochastic nature of choice determination. So, we used inverse binomial sampling (IBS; [61]), an efficient way of generating unbiased estimates via numerical simulations. The maximum-likelihood estimate of the model parameters was obtained with Bayesian Adaptive Direct Search (BADS) [62], a hybrid Bayesian optimization to find the parameter vector that maximizes the log likelihood, which works well with stochastic target functions. To reduce the risk of being stuck at local optima, we repeated 20 independent fittings by setting the starting positions randomly using Latin hypercube sampling (lhsdesign_modifed.m by Nassim Khlaled; https://www.mathworks.com/matlabcentral/fileexchange/45793-latin-hypercube) and then picked the fitting with the highest log likelihood. To avoid infinite loops from using IBS, we did not impose individual lapse rates in an arbitrary manner. Instead, we calculated the average of the lapse rate and guess rate from the cumulative Gaussian fit to a given individualʼs grand mean (based on the entire trials) psychometric curve. With these individual lapse probabilities (mean rate of 0.05, which ranged [0.0051, 0.1714]), trials were randomly designated as lapse trials, in which the choice was randomly determined to be either small or large.

Ci,j,k

LL

θ∗

Model comparison in goodness of fit

We compared the goodness of fit of the models using AICc based on maximum-likelihood estimation fitting, as follows:

2p(p + 1) (NxMxK) − p − 1

AICc = −2 ⋅ LL(θ∗) + 2p +

where is the number of parameters of the model and the total number of trials in the dataset is
