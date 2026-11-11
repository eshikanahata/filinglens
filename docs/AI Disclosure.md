# FilingLens: Disclosure of AI Tool Use

Eshika Nahata (DA24B004)

This document states how AI tools were used in building FilingLens, what was done by me, and how AI-assisted work was checked.

## 1. Summary

I used an AI assistant (Claude, by Anthropic) during this project for code review, debugging and implementing some components and for editing the design and test documents. I reviewed, ran and tested all code myself; every result reported in this project comes from my own runs of the pipeline and tests. The design decisions and their justification are my own, and I am responsible for the content.

## 2. Tool used

| Tool | Provider | Used for |
| --- | --- | --- |
| Claude (chat assistant) | Anthropic | Code review, debugging, code changes, documentation editing |

No AI model is part of the FilingLens application itself apart from the project's own trained models (logistic regression and XGBoost), which were trained on the project's data by the project's pipeline.

## 4. What AI was not used for

- **Results.** Every number in the documents (dataset sizes, parse rates, model scores and intervals, benchmark, latency, drift results, test counts) comes from my own runs of the pipeline, tests and scripts. None was generated or estimated by the assistant.
- **Evidence.** All screenshots were captured by me from the running system.
- **Data.** The filings, prices and labels come only from the sources named in the report.

## 5. How AI-assisted work was checked

- All code, including AI-written code, passes the project's automated test suite (130 tests) and the flake8 style check, which run before every commit.
- Each change was run on the real pipeline and the Docker deployment, and the 27 manual system tests were performed on the final system.
- Where the assistant's suggestion was wrong or incomplete, the failure was found by running it and was corrected before committing; these cases are recorded in the Test Report where relevant.

## 6. Responsibility

I am responsible for the design, the code and the content of all deliverables, and I can explain and defend each part of the system.
