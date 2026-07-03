
===== MODEL: GLM-OCR =====
PLOS Biology | https://doi.org/10.1371/journal.pbio.3002373 November 8, 2023 20 / 32

PLOS BIOLOGY Corrective feedback on perceptual decisions

Fig 2B) stimulus duration—at the moment of updating the state of the class boundary (as will be shown below in the subsection titled “Boundary-updating”) and instead must be retrieved from the working memory system. The mnemonic recall of the stimulus is known to be noisy, becoming quickly deteriorated right away after stimulus offset, especially for continuous visual evidence such as color and orientation [56,57]. The generative process relating $m$ to $m'$ has been adopted for the same reason by recent studies [58,59], including our group [55], and is consistent with the nonzero levels of memory noise in the model-fit results ($\sigma_{m'}^2 = [1.567, 5.606]$). The substantial across-individual variability of the fitted levels of $\sigma_{m'}^2$ is also consistent with the previous studies [55,58,59].

With the learned generative model defined above, the decision-maker commits to a decision by inferring the current state of the class variable $CL$ from the current sensory measurement $m$ and then updates the current state of the boundary variable from both the current mnemonic measurement $m'$ and the current feedback $F$.

Decision-making. As for decision-making, BMBU, unlike the belief-based RL model, does not consider the choice values but completely relies on the $p$-computation by selecting the large class if $p_L > 0.5$ and the small class if $p_L < 0.5$. The $p$-computation is carried out by propagating the sensory measurement $m$ within its learned generative model:

$$p_L = \int_{\hat{B}}^\infty p(S|m)dS, \quad (7)$$

where the finite limit of the integral is defined by the inferred state of the boundary $\hat{B}$, which is continually updated on a trial-to-trial basis (as will be described below). This means that the behavioral choice can vary depending on $\hat{B}$ even for the same value of $m$ (as depicted in the “perception” stage of Fig 3A and 3B).

Boundary-updating. After having experienced a PDM episode in any given trial $t$, BMBU (i) computes the likelihood of the class boundary by concurrently propagating the mnemonic measurement $m'_t$ and the “informed” state of the class variable $CL_t$, which can be informed by feedback $F_t$ and choice $C_t$ in the current PDM episode, within its learned generative model ($p(m'_t, CL_t|B_t)$) and then (ii) forms a posterior distribution of the class boundary ($p(B_t|m'_t, CL_t)$) by combining that likelihood with its prior belief about the class boundary at the moment ($p(B_t)$), which is inherited from the posterior distribution formed in the previous trial $t - 1(p(B_{t-1}|m'_{t-1}, CL_{t-1}))$. Intuitively put, as BMBU undergoes successive trials, its posterior belief in the previous trial becomes the prior in the current trial, being used as the class boundary for decision-making and then being combined with the likelihood to be updated as the posterior belief in the current trial. Below, we will first describe the computations for (i) and then those for (ii). As

===== MODEL: PaddleOCR-VL =====
PLOS Biology | https://doi.org/10.1371/journal.pbio.3002373 November 8, 2023 20 / 32
PLOS BIOLOGY Corrective feedback on perceptual decisions
Fig 2B) stimulus duration-at the moment of updating the state of the class boundary (as will be shown below in the subsection titled 'Boundary-updating') and instead must be retrieved from the working memory system. The mnemonic recall of the stimulus is known to be noisy, becoming quickly deteriorated right away after stimulus offset, especially for continuous visual evidence such as color and orientation [56,57]. The generative process relating m to m' has been adopted for the same reason by recent studies [58,59], including our group [55], and is consistent with the nonzero levels of memory noise in the modelfit results (σ 2m' = [1.567, 5.606]). The substantial across-individual variability of the fitted levels of σ 2m' is also consistent with the previous studies [55,58,59].
With the learned generative model defined above, the decision-maker commits to a deci- sion by inferring the current state of the class variable CL from the current sensory measure- ment m and then updates the current state of the boundary variable from both the current mnemonic measurement m' and the current feedback F.
Decision-making. As for decision-making, BMU, unlike the belief-based RL model, does not consider the choice values but completely relies on the p-computation by selecting the large class if p L > 0.5 and the small class if p L
p L = ∫ ∞ ∂ p (S | m) dS, (7)
where the finite limit of the integral is defined by the inferred state of the boundary ˆ B , which is continually updated on a trial-to-trial basis (as will be described below). This means that the behavioral choice can vary depending on ˆ B even for the same value of m (as depicted in the 'perception' stage of Fig 3A and 3B).
Boundary-updating. After having experienced a PDM episode in any given trial t, BMU (i) computes the likelihood of the class boundary by concurrently propagating the mnemonic measurement m 1t 'informed' state of the class variable CL t , which can be informed by feedback F t and choice C t in the current PDM episode, within its learned generative model (p (m 1t , CL t | B t )) and then (ii) forms a posterior distribution of the class boundary (p (B t | m 1t , CL t )) by combining that likelihood with its prior belief about the class boundary at the moment (p (B t )) , which is inherited from the posterior distribution formed in the previous trial t - 1 (p (B t -1 | m 1t -1 , CL t -1 )) . Intuitively put, as BMU undergoes successive trials, its poste- rior belief in the previous trial becomes the prior in the current trial, being used as the class boundary for decision-making and then being combined with the likelihood to be updated as the posterior belief in the current trial. Below, we will first describe the computations for (i) and then those for (ii). As

===== MODEL: olmOCR-2-FP8 =====
---
primary_language: en
is_rotation_valid: True
rotation_correction: 0
is_table: False
is_diagram: False
---
Fig 2B) stimulus duration—at the moment of updating the state of the class boundary (as will be shown below in the subsection titled “Boundary-updating”) and instead must be retrieved from the working memory system. The mnemonic recall of the stimulus is known to be noisy, becoming quickly deteriorated right away after stimulus offset, especially for continuous visual evidence such as color and orientation [56,57]. The generative process relating \( m \) to \( m' \) has been adopted for the same reason by recent studies [58,59], including our group [55], and is consistent with the nonzero levels of memory noise in the model-fit results (\( \sigma_{m'}^2 = [1.567, 5.606] \)). The substantial across-individual variability of the fitted levels of \( \sigma_{m'}^2 \) is also consistent with the previous studies [55,58,59].

With the learned generative model defined above, the decision-maker commits to a decision by inferring the current state of the class variable \( CL \) from the current sensory measurement \( m \) and then updates the current state of the boundary variable from both the current mnemonic measurement \( m' \) and the current feedback \( F \).

**Decision-making.** As for decision-making, BMBU, unlike the belief-based RL model, does not consider the choice values but completely relies on the \( p \)-computation by selecting the *large* class if \( p_L > 0.5 \) and the *small* class if \( p_L < 0.5 \). The \( p \)-computation is carried out by propagating the sensory measurement \( m \) within its learned generative model:

\[
p_L = \int_{\hat{B}}^\infty p(S|m)dS,
\]

where the finite limit of the integral is defined by the inferred state of the boundary \( \hat{B} \), which is continually updated on a trial-to-trial basis (as will be described below). This means that the behavioral choice can vary depending on \( \hat{B} \) even for the same value of \( m \) (as depicted in the “perception” stage of Fig 3A and 3B).

**Boundary-updating.** After having experienced a PDM episode in any given trial \( t \), BMBU (i) computes the likelihood of the class boundary by concurrently propagating the mnemonic measurement \( m'_t \) and the “informed” state of the class variable \( CL_t \), which can be informed by feedback \( F_t \) and choice \( C_t \) in the current PDM episode, within its learned generative model (\( p(m'_t, CL_t|B_t) \)) and then (ii) forms a posterior distribution of the class boundary (\( p(B_t|m'_t, CL_t) \)) by combining that likelihood with its prior belief about the class boundary at the moment (\( p(B_t) \)), which is inherited from the posterior distribution formed in the previous trial \( t-1 \) (\( p(B_{t-1}|m'_{t-1}, CL_{t-1}) \)). Intuitively put, as BMBU undergoes successive trials, its posterior belief in the previous trial becomes the prior in the current trial, being used as the class boundary for decision-making and then being combined with the likelihood to be updated as the posterior belief in the current trial. Below, we will first describe the computations for (i) and then those for (ii). As

===== MODEL: chandra-2 =====
<div data-bbox="25 0 796 19" data-label="Page-Header">PLOS Biology | <a href="https://doi.org/10.1371/journal.pbio.3002373">https://doi.org/10.1371/journal.pbio.3002373</a> November 8, 2023 20 / 32</div>
<div data-bbox="25 42 570 61" data-label="Page-Header">PLOS BIOLOGY Corrective feedback on perceptual decisions</div>
<div data-bbox="25 81 981 270" data-label="Text">
<p>Fig 2B) stimulus duration—at the moment of updating the state of the class boundary (as will be shown below in the subsection titled “Boundary-updating”) and instead must be retrieved from the working memory system. The mnemonic recall of the stimulus is known to be noisy, becoming quickly deteriorated right away after stimulus offset, especially for continuous visual evidence such as color and orientation [56,57]. The generative process relating <math>m</math> to <math>m'</math> has been adopted for the same reason by recent studies [58,59], including our group [55], and is consistent with the nonzero levels of memory noise in the model-fit results (<math>\sigma_{m'}^2 = [1.567, 5.606]</math>). The substantial across-individual variability of the fitted levels of <math>\sigma_{m'}^2</math> is also consistent with the previous studies [55,58,59].</p>
</div>
<div data-bbox="25 289 978 381" data-label="Text">
<p>With the learned generative model defined above, the decision-maker commits to a decision by inferring the current state of the class variable <math>CL</math> from the current sensory measurement <math>m</math> and then updates the current state of the boundary variable from both the current mnemonic measurement <math>m'</math> and the current feedback <math>F</math>.</p>
</div>
<div data-bbox="25 400 976 493" data-label="Text">
<p><b>Decision-making.</b> As for decision-making, BMBU, unlike the belief-based RL model, does not consider the choice values but completely relies on the <math>p</math>-computation by selecting the <i>large</i> class if <math>p_L &gt; 0.5</math> and the <i>small</i> class if <math>p_L &lt; 0.5</math>. The <math>p</math>-computation is carried out by propagating the sensory measurement <math>m</math> within its learned generative model:</p>
</div>
<div data-bbox="357 510 631 556" data-label="Equation-Block">
<math display="block">p_L = \int_{\hat{B}}^{\infty} p(S|m) dS, \quad (7)</math>
</div>
<div data-bbox="25 574 978 673" data-label="Text">
<p>where the finite limit of the integral is defined by the inferred state of the boundary <math>\hat{B}</math>, which is continually updated on a trial-to-trial basis (as will be described below). This means that the behavioral choice can vary depending on <math>\hat{B}</math> even for the same value of <math>m</math> (as depicted in the “perception” stage of Fig 3A and 3B).</p>
</div>
<div data-bbox="25 692 979 929" data-label="Text">
<p><b>Boundary-updating.</b> After having experienced a PDM episode in any given trial <math>t</math>, BMBU (i) computes the likelihood of the class boundary by concurrently propagating the mnemonic measurement <math>m'_t</math> and the “informed” state of the class variable <math>CL_t</math>, which can be informed by feedback <math>F_t</math> and choice <math>C_t</math> in the current PDM episode, within its learned generative model (<math>p(m'_t, CL_t|B_t)</math>) and then (ii) forms a posterior distribution of the class boundary (<math>p(B_t|m'_t, CL_t)</math>) by combining that likelihood with its prior belief about the class boundary at the moment (<math>p(B_t)</math>), which is inherited from the posterior distribution formed in the previous trial <math>t - 1</math> (<math>p(B_{t-1}|m'_{t-1}, CL_{t-1})</math>). Intuitively put, as BMBU undergoes successive trials, its posterior belief in the previous trial becomes the prior in the current trial, being used as the class boundary for decision-making and then being combined with the likelihood to be updated as the posterior belief in the current trial. Below, we will first describe the computations for 

===== MODEL: DeepSeek-OCR =====
<|ref|>text<|/ref|><|det|>[[26, 40, 570, 60]]<|/det|>
PLOS BIOLOGY Corrective feedback on perceptual decisions  

<|ref|>text<|/ref|><|det|>[[24, 78, 972, 271]]<|/det|>
Fig 2B) stimulus duration- at the moment of updating the state of the class boundary (as will be shown below in the subsection titled "Boundary- updating") and instead must be retrieved from the working memory system. The mnemonic recall of the stimulus is known to be noisy, becoming quickly deteriorated right away after stimulus offset, especially for continuous visual evidence such as color and orientation [56,57]. The generative process relating \(m\) to \(m'\) has been adopted for the same reason by recent studies [58,59], including our group [55], and is consistent with the nonzero levels of memory noise in the model- fit results \((\sigma_{m'}^{2} = [1.567,5.606])\) . The substantial across- individual variability of the fitted levels of \(\sigma_{m'}^{2}\) is also consistent with the previous studies [55,58,59].  

<|ref|>text<|/ref|><|det|>[[25, 287, 968, 382]]<|/det|>
With the learned generative model defined above, the decision- maker commits to a deci- sion by inferring the current state of the class variable \(CL\) from the current sensory measure- ment \(m\) and then updates the current state of the boundary variable from both the current mnemonic measurement \(m'\) and the current feedback \(F\) .  

<|ref|>text<|/ref|><|det|>[[25, 399, 965, 494]]<|/det|>
Decision- making. As for decision- making, BMBU, unlike the belief- based RL model, does not consider the choice values but completely relies on the \(p\) - computation by selecting the large class if \(p_{L} > 0.5\) and the small class if \(p_{L} < 0.5\) . The \(p\) - computation is carried out by propagating the sensory measurement \(m\) within its learned generative model:  

<|ref|>equation<|/ref|><|det|>[[362, 508, 633, 558]]<|/det|>
\[p_{L} = \int_{\hat{B}}^{\infty}p(S|m)dS, \quad (7)\]  

<|ref|>text<|/ref|><|det|>[[25, 573, 967, 672]]<|/det|>
where the finite limit of the integral is defined by the inferred state of the boundary \(\hat{B}\) , which is continually updated on a trial- to- trial basis (as will be described below). This means that the behavioral choice can vary depending on \(\hat{B}\) even for the same value of \(m\) (as depicted in the "perception" stage of Fig 3A and 3B).  

<|ref|>text<|/ref|><|det|>[[24, 689, 970, 931]]<|/det|>
Boundary- updating. After having experienced a PDM episode in any given trial \(t\) , BMBU (i) computes the likelihood of the class boundary by concurrently propagating the mnemonic measurement \(m_{t}^{\prime}\) and the "informed" state of the class variable \(CL_{t}\) , which can be informed by feedback \(F_{t}\) and choice \(C_{t}\) in the current PDM episode, within its learned generative model \((p(m_{t}^{\prime},CL_{t}|B_{t}))\) and then (ii) forms a posterior distribution of the class boundary \((p(B_{t}|m_{t}^{\prime},CL_{t}))\) by combining that likelihood with its prior belief about the class boundary at the moment \((p(B_{t}))\) , which is inherited from the posterior distribution formed in the previous trial \(t - 1(p(B_{t - 1}|m_{t - 1}^{\prime},CL_{t - 1}))\) . Intuitively put, as BMBU undergoes successive trials, its poste- rior belief in the previous trial becomes the prior in the current trial, being used as the class boundary for decision- making and then being combined with the likelihood to be updated as the posterior belief in the current trial. Below, we will first describe the computations for (i) and then those for (ii). As

===== MODEL: Nanonets-OCR2 =====
PLOS Biology | https://doi.org/10.1371/journal.pbio.3002373 November 8, 2023 <page_number>20 / 32</page_number>

PLOS BIOLOGY Corrective feedback on perceptual decisions

Fig 2B) stimulus duration—at the moment of updating the state of the class boundary (as will be shown below in the subsection titled “Boundary-updating”) and instead must be retrieved from the working memory system. The mnemonic recall of the stimulus is known to be noisy, becoming quickly deteriorated right away after stimulus offset, especially for continuous visual evidence such as color and orientation [56,57]. The generative process relating $m$ to $m'$ has been adopted for the same reason by recent studies [58,59], including our group [55], and is consistent with the nonzero levels of memory noise in the model-fit results ($\sigma_{m'}^2 = [1.567, 5.606]$). The substantial across-individual variability of the fitted levels of $\sigma_{m'}^2$ is also consistent with the previous studies [55,58,59].

With the learned generative model defined above, the decision-maker commits to a decision by inferring the current state of the class variable $CL$ from the current sensory measurement $m$ and then updates the current state of the boundary variable from both the current mnemonic measurement $m'$ and the current feedback $F$.

**Decision-making.** As for decision-making, BMBU, unlike the belief-based RL model, does not consider the choice values but completely relies on the $p$-computation by selecting the *large* class if $p_L > 0.5$ and the *small* class if $p_L < 0.5$. The $p$-computation is carried out by propagating the sensory measurement $m$ within its learned generative model:

$$p_L = \int_{\hat{B}}^{\infty} p(S|m)dS, \quad (7)$$

where the finite limit of the integral is defined by the inferred state of the boundary $\hat{B}$, which is continually updated on a trial-to-trial basis (as will be described below). This means that the behavioral choice can vary depending on $\hat{B}$ even for the same value of $m$ (as depicted in the “perception” stage of Fig 3A and 3B).

**Boundary-updating.** After having experienced a PDM episode in any given trial $t$, BMBU (i) computes the likelihood of the class boundary by concurrently propagating the mnemonic measurement $m'_t$ and the “informed” state of the class variable $CL_t$, which can be informed by feedback $F_t$ and choice $C_t$ in the current PDM episode, within its learned generative model ($p(m'_t, CL_t|B_t)$) and then (ii) forms a posterior distribution of the class boundary ($p(B_t|m'_t, CL_t)$) by combining that likelihood with its prior belief about the class boundary at the moment ($p(B_t)$), which is inherited from the posterior distribution formed in the previous trial $t-1$ ($p(B_{t-1}|m'_{t-1}, CL_{t-1})$). Intuitively put, as BMBU undergoes successive trials, its posterior belief in the previous trial becomes the prior in the current trial, being used as the class boundary for decision-making and then being combined with the likelihood to be updated as the posterior belief in the current trial. Below, we will first describe the computations for (i) and then those for (ii). As

===== MODEL: Nemotron-Parse =====
<x_0.1533><y_0.1156>\begin{tabular}{ccccc}
 & **100.05** & **200.07** & **200.08** & **200.09**\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.08}\\
\multicolumn{4}{c}{17} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{18} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{19} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4}{c}{20} & \multicolumn{2}{c}{200.09}\\
\multicolumn{4
