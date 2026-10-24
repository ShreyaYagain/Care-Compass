# External Data Sources

Date accessed: 2026-10-24

## TriageBench
- Title: TriageBench — consistency/bias benchmark for clinical triage
- Repo: https://github.com/wongqihan/triagebench
- Dataset: https://huggingface.co/datasets/wongqihan/triagebench
- Licence: MIT
- What we use it for: **fairness / consistency harness only.** The same clinical
  vignette is repeated with one irrelevant detail swapped (gender, language, ZIP
  code). It has **NO ground-truth care-type labels**, so we report "consistency",
  never "accuracy". (See docs/FAIRNESS_REPORT.md.)
- TriageBench: 14 HF rows (probes: gender/language/zipcode); vignettes + translations also in raw/triagebench repo.

## MedSumm / MMCQS
- Title: MMCQS (Multi-modal Code-mixed Question Summarization) / MedSumm
- Repo: https://github.com/ArkadeepAcharya/MedSumm-ECIR2024
- Dataset: https://huggingface.co/datasets/ArkaAcharya/MMCQSD
- Licence: CC-BY-4.0 (per the Hugging Face dataset card; the repo README does not
  state one)
- What we use it for: Hinglish vocabulary mining, robustness runs, and short
  few-shot examples for Groq extraction. It has **NO care-type labels**. We do
  not redistribute the text.
- MMCQS: 3015 HF rows; language mix {'hinglish': 2990, 'en': 3, 'hi': 22}.

## Citation (BibTeX, from each repo's README)
```bibtex
@misc{wong2026gender,
  title  = {Gender-Dependent Diagnostic Substitution in LLM Medical Triage: Same Symptoms, Unequal Urgency},
  author = {Wong, Qi Han},
  year   = {2026},
  eprint = {2606.03641},
  archivePrefix = {arXiv}
}
```
