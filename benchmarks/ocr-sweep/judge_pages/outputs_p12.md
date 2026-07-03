
===== MODEL: GLM-OCR =====
represent the ways the history factors (feedback and stimulus) exert their contribution to choice bias. In the right panels, $PSE_{toi+1}$, which quantifies the choice bias in the trials following a certain PDM episode at $toi = [0; large; correct]$, is plotted as a function of the stimulus size at $toi$. The color indicates the direction of choice bias, as in (B) and (C).

https://doi.org/10.1371/journal.pbio.3002373.g003

$$\delta = r - Q_{large(small)} = r - p(CL = large(small)) \times V_{large(small)},$$

where $\alpha, \delta$, and $r$ are the learning rate, the reward prediction error, and the reward, respectively. The state of feedback determines the value of $r$: $r = 1$ for correct; $r = 0$ for incorrect. Note that $\delta$ has the statistical decision confidence at the perception stage, i.e., $p(CL = large(small))$, as one of its 3 arguments. As stressed by the authors who developed this algorithm [9], this feature makes the strength of sensory evidence—i.e., statistical decision confidence—modulate.

PLOS Biology | https://doi.org/10.1371/journal.pbio.3002373 November 8, 2023 7 / 32

the degree to which the decision-maker updates the chosen value based on feedback (Fig 3E, left). Hence, this belief (confidence)-based modulation of value-updating underlies the stimulus-dependent feedback effects: The amount of feedback effects decreases as sensory evidence becomes stronger since the reward prediction error decreases as a function of $p(CL = large(small))$, which is proportional to sensory evidence (Fig 3E, right).

The Bayesian model of boundary-updating (BMBU)

To implement the world-updating scenario, we developed BMBU, which updates the class boundary based on the previous PDM episode in the framework of BDT. Specifically, given “a state of the class variable that is indicated jointly by feedback and choice,” CL, and “a noisy memory recall of the sensory measurement (which will be referred to as ‘mnemonic measurement’ hereinafter),” $m',$ BMBU infers the mean of the size distribution (i.e., class boundary), $B$, by updating its prior belief about $B, p(B)$, with the likelihood of $B, p(m', CL|B)$, by inverting its learned generative model of how $m'$ and CL are generated (Fig 3D, left; Eqs 3–6 in Materials and methods for the detailed formalisms for the learned generative model), as follows:

$$p(B|m', CL) \propto p(m', CL|B)p(B) \equiv p(m', C, F|B)p(B):$$

This inference uses multiple pieces of information from the PDM episode just experienced, including the mnemonic measurement, choice, and feedback, to update the belief about the location of the class boundary (refer to Eqs 8–14 in Materials and methods for more detailed formalisms for the inference). In what follows, we will explain why and how this inference leads to the specific stimulus-dependent feedback effects predicted by the world-updating scenario (Fig 3D, right), where world knowledge is continuously updated.

===== MODEL: PaddleOCR-VL =====
represent the ways the history factors (feedback and stimulus) exert their contribution to choice bias. In the right panels, PSE toi+1 , which quantifies the choice bias in the trials following a certain PDM episode at toi = [0; large; correct] , is plotted as a function of the stimulus size at toi . The color indicates the direction of choice bias, as in (B) and (C).
https://doi.org/10.1371/journal.pbio.3002373.g003
δ = r - Q large (small) = r - p (CL = large (small)) × V large (small) ,
where α, δ, and r are the learning rate, the reward prediction error, and the reward, respectively. The state of feedback determines the value of r: r = 1 for correct; r = 0 for incorrect. Note that δ has the statistical decision confidence at the perception stage, i.e., p (CL = large (small)), as one of its 3 arguments. As stressed by the authors who developed this algorithm [9], this feature makes the strength of sensory evidence-i.e., statistical decision confidence-modulate
PLOS Biology | https://doi.org/10.1371/journal.pbio.3002373 November 8, 2023 7 / 32
the degree to which the decision-maker updates the chosen value based on feedback (Fig 3E, left). Hence, this belief (confidence)-based modulation of value-updating underlies the stimulus-dependent feedback effects: The amount of feedback effects decreases as sensory evidence becomes stronger since the reward prediction error decreases as a function of p (CL = large (small)), which is proportional to sensory evidence (Fig 3E, right).
The Bayesian model of boundary-updating (BMCU)
To implement the world-updating scenario, we developed BMCU, which updates the class boundary based on the previous PDM episode in the framework of BDT. Specifically, given 'a state of the class variable that is indicated jointly by feedback and choice,' CL, and 'a noisy memory recall of the sensory measurement (which will be referred to as 'mnemonic measurement' hereinafter),' m', BMCU infers the mean of the size distribution (i.e., class boundary), B, by updating its prior belief about B, p (B), with the likelihood of B, p (m', CL|B), by inverting its learned generative model of how m' and CL are generated (Fig 3D, left; Eqs 3-6 in Materials and methods for the detailed formalisms for the learned generative model), as follows:
p (B|m', CL) ∝ p (m', CL|B)p (B) ≡ p (m', C, F|B)p (B) :
This inference uses multiple pieces of information from the PDM episode just experienced, including the mnemonic measurement, choice, and feedback, to update the belief about the location of the class boundary (refer to Eqs 8-14 in Materials and methods for more detailed formalisms for the inference). In what follows, we will explain why and how this inference leads to the specific stimulus-dependent feedback effects predicted by the world-updating scenario (Fig 3D, right), where world knowledge is continuously updated.

===== MODEL: olmOCR-2-FP8 =====
---
primary_language: en
is_rotation_valid: True
rotation_correction: 0
is_table: False
is_diagram: False
---
represent the ways the history factors (feedback and stimulus) exert their contribution to choice bias. In the right panels, \( PSE_{toi+1} \), which quantifies the choice bias in the trials following a certain PDM episode at \( toi = [0; large; correct] \), is plotted as a function of the stimulus size at \( toi \). The color indicates the direction of choice bias, as in (B) and (C).

https://doi.org/10.1371/journal.pbio.3002373.g003

\[
\delta = r - Q_{large(small)} = r - p(CL = large(small)) \times V_{large(small)},
\]

where \( \alpha, \delta, \) and \( r \) are the learning rate, the reward prediction error, and the reward, respectively. The state of feedback determines the value of \( r \): \( r = 1 \) for correct; \( r = 0 \) for incorrect. Note that \( \delta \) has the statistical decision confidence at the perception stage, i.e., \( p(CL = large(small)) \), as one of its 3 arguments. As stressed by the authors who developed this algorithm [9], this feature makes the strength of sensory evidence—i.e., statistical decision confidence—modulate

the degree to which the decision-maker updates the chosen value based on feedback (Fig 3E, left). Hence, this belief (confidence)-based modulation of value-updating underlies the stimulus-dependent feedback effects: The amount of feedback effects decreases as sensory evidence becomes stronger since the reward prediction error decreases as a function of \( p(CL = large (small)) \), which is proportional to sensory evidence (Fig 3E, right).

The Bayesian model of boundary-updating (BMBU)

To implement the world-updating scenario, we developed BMBU, which updates the class boundary based on the previous PDM episode in the framework of BDT. Specifically, given “a state of the class variable that is indicated jointly by feedback and choice,” CL, and “a noisy memory recall of the sensory measurement (which will be referred to as ‘mnemonic measurement’ hereinafter),” \( m' \), BMBU infers the mean of the size distribution (i.e., class boundary), \( B \), by updating its prior belief about \( B, p(B) \), with the likelihood of \( B, p(m', CL|B) \), by inverting its learned generative model of how \( m' \) and CL are generated (Fig 3D, left; Eqs 3–6 in Materials and methods for the detailed formalisms for the learned generative model), as follows:

\[
p(B|m', CL) \propto p(m', CL|B)p(B) \equiv p(m', C, F|B)p(B) :
\]

This inference uses multiple pieces of information from the PDM episode just experienced, including the mnemonic measurement, choice, and feedback, to update the belief about the location of the class boundary (refer to Eqs 8–14 in Materials and methods for more detailed formalisms for the inference). In what follows, we will explain why and how this inference leads to the specific stimulus-dependent feedback effects predicted by the world-updating scenario (Fig 3D, right), where world knowledge is continuously updated.

===== MODEL: chandra-2 =====
<div data-bbox="22 0 960 93" data-label="Text"><p>represent the ways the history factors (feedback and stimulus) exert their contribution to choice bias. In the right panels, <math>PSE_{toi+1}</math>, which quantifies the choice bias in the trials following a certain PDM episode at <math>toi = [0; large; correct]</math>, is plotted as a function of the stimulus size at <math>toi</math>. The color indicates the direction of choice bias, as in (B) and (C).</p></div><div data-bbox="22 111 473 131" data-label="Text"><p><a href="https://doi.org/10.1371/journal.pbio.3002373.g003">https://doi.org/10.1371/journal.pbio.3002373.g003</a></p></div><div data-bbox="182 148 812 173" data-label="Equation-Block"><math display="block">\delta = r - Q_{large(small)} = r - p(CL = large(small)) \times V_{large(small)},</math></div><div data-bbox="22 191 971 308" data-label="Text"><p>where <math>\alpha</math>, <math>\delta</math>, and <math>r</math> are the learning rate, the reward prediction error, and the reward, respectively. The state of feedback determines the value of <math>r</math>: <math>r = 1</math> for correct; <math>r = 0</math> for incorrect. Note that <math>\delta</math> has the statistical decision confidence at the perception stage, i.e., <math>p(CL = large(small))</math>, as one of its 3 arguments. As stressed by the authors who developed this algorithm [9], this feature makes the strength of sensory evidence—i.e., statistical decision confidence—modulate</p></div><div data-bbox="22 327 783 348" data-label="Text"><p>PLOS Biology | <a href="https://doi.org/10.1371/journal.pbio.3002373">https://doi.org/10.1371/journal.pbio.3002373</a> November 8, 2023 7 / 32</p></div><div data-bbox="22 367 940 484" data-label="Text"><p>the degree to which the decision-maker updates the chosen value based on feedback (Fig 3E, left). Hence, this belief (confidence)-based modulation of value-updating underlies the stimulus-dependent feedback effects: The amount of feedback effects decreases as sensory evidence becomes stronger since the reward prediction error decreases as a function of <math>p(CL = large(small))</math>, which is proportional to sensory evidence (Fig 3E, right).</p></div><div data-bbox="22 531 913 562" data-label="Section-Header"><h2>The Bayesian model of boundary-updating (BMBU)</h2></div><div data-bbox="22 596 963 785" data-label="Text"><p>To implement the world-updating scenario, we developed BMBU, which updates the class boundary based on the previous PDM episode in the framework of BDT. Specifically, given “a state of the class variable that is indicated jointly by feedback and choice,” <math>CL</math>, and “a noisy memory recall of the sensory measurement (which will be referred to as ‘mnemonic measurement’ hereinafter),” <math>m'</math>, BMBU infers the mean of the size distribution (i.e., class boundary), <math>B</math>, by updating its prior belief about <math>B</math>, <math>p(B)</math>, with the likelihood of <math>B</math>, <math>p(m', CL|B)</math>, by inverting its learned generative model of how <math>m'</math> and <math>CL</math> are generated (Fig 3D, left; Eqs 3–6 in Materials and methods for the detailed formalisms for the learned generative model), as follows:</p></div><div data-bbox="22 803 587 826" data-label="Equation-Block"><math display="block">p(B|m', CL) \propto p(m', CL|B)p(B) \equiv p(m', C, F|B)p(B) :</math></div><div data-bbox="22 844 953 985" data-label="Text"><p>This inference uses multiple pieces of information from the PDM episode just experienced, including the mnemonic measurement, choice, and feedback, to update the belief about the location of the class boundary (refer to Eqs 8–14 in Materials and methods for more detailed formalisms for the inference). In what follows, we will explain why and how this inference leads to the specific stimulus-dependent feedback effects predicted by the world-updating scenario (Fig 3D, right), where world knowledge is continuously updated.</p></div>

===== MODEL: DeepSeek-OCR =====
<|ref|>text<|/ref|><|det|>[[25, 0, 960, 95]]<|/det|>
represent the ways the history factors (feedback and stimulus) exert their contribution to choice bias. In the right panels, \(PSE_{toi + 1}\) , which quantifies the choice bias in the trials following a certain PDM episode at \(toi = [0; large; correct]\) , is plotted as a function of the stimulus size at \(toi\) . The color indicates the direction of choice bias, as in (B) and (C).  

<|ref|>text<|/ref|><|det|>[[25, 111, 480, 133]]<|/det|>
https://doi.org/10.1371/journal.pbio.3002373. g003  

<|ref|>equation<|/ref|><|det|>[[184, 149, 812, 177]]<|/det|>
\[\delta = r - Q_{large(small)} = r - p(CL = large(small))\times V_{large(small)},\]  

<|ref|>text<|/ref|><|det|>[[25, 192, 970, 310]]<|/det|>
where \(\alpha , \delta\) , and \(r\) are the learning rate, the reward prediction error, and the reward, respectively. The state of feedback determines the value of \(r\) : \(r = 1\) for correct; \(r = 0\) for incorrect. Note that \(\delta\) has the statistical decision confidence at the perception stage, i.e., \(p(CL = large(small))\) , as one of its 3 arguments. As stressed by the authors who developed this algorithm [9], this feature makes the strength of sensory evidence—i.e., statistical decision confidence—modulate  

<|ref|>text<|/ref|><|det|>[[27, 328, 784, 351]]<|/det|>
PLOS Biology | https://doi.org/10.1371/journal.pbio.3002373 November 8, 2023 7 / 32  

<|ref|>text<|/ref|><|det|>[[25, 367, 940, 489]]<|/det|>
the degree to which the decision- maker updates the chosen value based on feedback (Fig 3E, left). Hence, this belief (confidence)- based modulation of value- updating underlies the stimulus- dependent feedback effects: The amount of feedback effects decreases as sensory evidence becomes stronger since the reward prediction error decreases as a function of \(p(CL = large(small))\) , which is proportional to sensory evidence (Fig 3E, right).  

<|ref|>sub_title<|/ref|><|det|>[[28, 530, 914, 566]]<|/det|>
## The Bayesian model of boundary-updating (BMBU)  

<|ref|>text<|/ref|><|det|>[[25, 594, 963, 787]]<|/det|>
To implement the world- updating scenario, we developed BMBU, which updates the class boundary based on the previous PDM episode in the framework of BDT. Specifically, given "a state of the class variable that is indicated jointly by feedback and choice," CL, and "a noisy memory recall of the sensory measurement (which will be referred to as 'mnemonic measurement' hereinafter)," \(m'\) , BMBU infers the mean of the size distribution (i.e., class boundary), \(B\) , by updating its prior belief about \(B\) , \(p(B)\) , with the likelihood of \(B\) , \(p(m', CL|B)\) , by inverting its learned generative model of how \(m'\) and CL are generated (Fig 3D, left; Eqs 3–6 in Materials and methods for the detailed formalisms for the learned generative model), as follows:  

<|ref|>equation<|/ref|><|det|>[[25, 802, 586, 830]]<|/det|>
\[p(B|m',CL)\propto p(m',CL|B)p(B)\equiv p(m',C,F|B)p(B):\]  

<|ref|>text<|/ref|><|det|>[[25, 843, 952, 985]]<|/det|>
This inference uses multiple pieces of information from the PDM episode just experienced, including the mnemonic measurement, choice, and feedback, to update the belief about the location of the class boundary (refer to Eqs 8–14 in Materials and methods for more detailed formalisms for the inference). In what follows, we will explain why and how this inference leads to the specific stimulus- dependent feedback effects predicted by the world- updating scenario (Fig 3D, right), where world knowledge is continuously updated.

===== MODEL: Nanonets-OCR2 =====
represent the ways the history factors (feedback and stimulus) exert their contribution to choice bias. In the right panels, $PSE_{toi+1}$, which quantifies the choice bias in the trials following a certain PDM episode at $toi = [0; large; correct]$, is plotted as a function of the stimulus size at $toi$. The color indicates the direction of choice bias, as in (B) and (C).

https://doi.org/10.1371/journal.pbio.3002373.g003

$$\delta = r - Q_{large(small)} = r - p(CL = large(small)) \times V_{large(small)},$$

where $\alpha$, $\delta$, and $r$ are the learning rate, the reward prediction error, and the reward, respectively. The state of feedback determines the value of $r$: $r = 1$ for correct; $r = 0$ for incorrect. Note that $\delta$ has the statistical decision confidence at the perception stage, i.e., $p(CL = large(small))$, as one of its 3 arguments. As stressed by the authors who developed this algorithm [9], this feature makes the strength of sensory evidence—i.e., statistical decision confidence—modulate

the degree to which the decision-maker updates the chosen value based on feedback (Fig 3E, left). Hence, this belief (confidence)-based modulation of value-updating underlies the stimulus-dependent feedback effects: The amount of feedback effects decreases as sensory evidence becomes stronger since the reward prediction error decreases as a function of $p(CL = large(small))$, which is proportional to sensory evidence (Fig 3E, right).

PLOS Biology | https://doi.org/10.1371/journal.pbio.3002373 November 8, 2023 7 / 32

# The Bayesian model of boundary-updating (BMBU)

To implement the world-updating scenario, we developed BMBU, which updates the class boundary based on the previous PDM episode in the framework of BDT. Specifically, given “a state of the class variable that is indicated jointly by feedback and choice,” CL, and “a noisy memory recall of the sensory measurement (which will be referred to as ‘mnemonic measurement’ hereinafter),” $m'$, BMBU infers the mean of the size distribution (i.e., class boundary), $B$, by updating its prior belief about $B$, $p(B)$, with the likelihood of $B$, $p(m',CL|B)$, by inverting its learned generative model of how $m'$ and CL are generated (Fig 3D, left; Eqs 3–6 in Materials and methods for the detailed formalisms for the learned generative model), as follows:

$$p(B|m',CL) \propto p(m',CL|B)p(B) \equiv p(m',C,F|B)p(B):$$

This inference uses multiple pieces of information from the PDM episode just experienced, including the mnemonic measurement, choice, and feedback, to update the belief about the location of the class boundary (refer to Eqs 8–14 in Materials and methods for more detailed formalisms for the inference). In what follows, we will explain why and how this inference leads to the specific stimulus-dependent feedback effects predicted by the world-updating scenario (Fig 3D, right), where world knowledge is continuously updated.

===== MODEL: Nemotron-Parse =====
<x_0.1533><y_0.1156>\begin{tabular}{ccccc}
 & **100.05** & **200.07** & **200.08** & **200.09**\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.04}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.05}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.08}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3}{c}{16} & \multicolumn{2}{c}{200.09}\\
\multicolumn{3
