p(m′t,CLt = small|Bt) = ∫

p(m′t|St)p(St|Bt)dSt;

p(m′t,CLt = large|Bt) = ∫

p(m′t|St)p(St|Bt)dSt (10)

p(m′t|St) = N(m′t;St,σ2m′ + σ2m) S → m → m′

where , according to the “chain” relations defined in the learned generative model ( in the left panel of Fig 3D; Eqs 5 and 6; see Equation S2 for derivations in Text in S1 Appendix). Eq 10 indicates that BMBU calculates how likely hypothetical boundary states bring about the mnemonic measurement ( ) while taking into account the informed state of the class variable ( ), by constraining the possible range of the stimulus states. To help readers intuitively appreciate these respective contribu- tions of the mnemonic measurement and the informed state of the class variable (feedback) to the boundary likelihood, we further elaborated on how Eq 9 is reduced to Eq 10 depending on the informed state of (see Text in SI Appendix and S1 Fig).

B → S → m → m′ B → CL ← S

CLt = small N(St;Bt,σ2S) p(m′t|St) = N(m′t;St,σ2m′ + σ2m)

Lastly, we evaluate the integral for in Eq 10 by substituting $p(S_t|B_t) = $ and , from the defined statistical knowledge in the

PLOS Biology | https://doi.org/10.1371/journal.pbio.3002373 November 8, 2023 22 / 32

PLOS BIOLOGY | Corrective feedback on perceptual decisions

learned generative model (Eq 3 and Eqs 5 and 6, respectively) and find:

p(m′t,CLt = small|Bt)

# 1 √2π( σ

σ2M+σ2S )

# 2 Mσ2S

Btσ2

tσ2

S σ2

+σ2 S

σ2 M

σ2 S

σ2

M+σ2

S dSt ×

e

# 1 √2π(σ2M + σ2S)

(Bt−m′

t)2 2(σ2

e−

+σ2 S

σ2M = σ2m′

where . For the other state in feedback, we evaluate the integral in the same manner and find:

p(m′t,CLt = large|Bt)

# 1 √2π( σ

σ2M+σ2S )

# 2 Mσ2S

Btσ2

tσ2

S σ2

+σ2 S

σ2 M

σ2 S

σ2 M

+σ2

S dSt ×

e

# 1 √2π(σ2M + σ2S)

(Bt−m′

t)2 2(σ2

e−

+σ2 S

Having calculated the likelihood of , we turn to describe (ii) how BMBU combines that likelihood with a prior distribution on trial , which forms a posterior distribution of according to Bayes rule:

Bt t Bt