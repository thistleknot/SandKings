
<h1 align="center">
  <a href="https://sakana.ai/drq">
    <img width="600" alt="Discovered ALife Simulations" src="https://pub.sakana.ai/drq/assets/png/github_teaser-min.png"></a><br>
</h1>


<h1 align="center">
Digital Red Queen: <br> Adversarial Program Evolution in Core War with LLMs
</h1>
<p align="center">
  📝 <a href="https://sakana.ai/drq">Blog</a> |
  🌐 <a href="https://pub.sakana.ai/drq">Paper</a> |
  📄 <a href="https://arxiv.org/abs/2601.03335">PDF</a>
</p>
<p align="center">
<!-- <a href="https://colab.research.google.com/github/SakanaAI/asal/blob/main/asal.ipynb" target="_parent"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"/></a> -->
</p>

[Akarsh Kumar](https://x.com/akarshkumar0101) $^{1}$ $^2$, [Ryan Bahlous-Boldi](https://x.com/RyanBoldi) $^{1}$, [Prafull Sharma](https://x.com/prafull7) $^{1}$, [Phillip Isola](https://x.com/phillip_isola) $^1$, [Sebastian Risi](https://x.com/risi1979) $^2$, [Yujin Tang](https://x.com/yujin_tang) $^2$, [David Ha](https://x.com/hardmaru) $^2$
<br>
$^1$ MIT, $^2$ Sakana AI

## Abstract
Large language models (LLMs) are increasingly being used to evolve solutions to problems in many domains, in a process inspired by biological evolution. However, unlike biological evolution, most LLM-evolution frameworks are formulated as static optimization problems, overlooking the open-ended adversarial dynamics that characterize real-world evolutionary processes. Here, we study Digital Red Queen (DRQ), a simple self-play algorithm that embraces these so-called "Red Queen" dynamics via continual adaptation to a changing objective. DRQ uses an LLM to evolve assembly-like programs, called warriors, which compete against each other for control of a virtual machine in the game of Core War, a Turing-complete environment studied in artificial life and connected to cybersecurity. In each round of DRQ, the model evolves a new warrior to defeat all previous ones, producing a sequence of adapted warriors. Over many rounds, we observe that warriors become increasingly general (relative to a set of held-out human warriors). Interestingly, warriors also become less behaviorally diverse across independent runs, indicating a convergence pressure toward a general-purpose behavioral strategy, much like convergent evolution in nature. This result highlights a potential value of shifting from static objectives to dynamic Red Queen objectives. Our work positions Core War as a rich, controllable sandbox for studying adversarial adaptation in artificial systems and for evaluating LLM-based evolution methods. More broadly, the simplicity and effectiveness of DRQ suggest that similarly minimal self-play approaches could prove useful in other more practical multi-agent adversarial domains, like real-world cybersecurity or combating drug resistance.


<div style="display: flex; justify-content: space-between;">
  <img src="https://pub.sakana.ai/drq/assets/png/github_teaser2-min.png" alt="Image 1" style="width: 100%;">
</div>

## Repo Description
This repo contains a minimalistic implementation of DRQ to get you started ASAP.
Everything is implemented in pure Python, with multiprocessing, making it decently fast.

The original Core War code is from https://github.com/rodrigosetti/corewar!

---
