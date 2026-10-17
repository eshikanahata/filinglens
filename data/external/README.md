# External data

`LM_MasterDictionary.csv` — Loughran-McDonald Master Dictionary (finance-specific
word lists: negative, positive, uncertainty, litigious).

1. Download the latest Master Dictionary CSV from the Notre Dame SRAF site
   (https://sraf.nd.edu, "Loughran-McDonald Master Dictionary"). Free for academic use;
   cite Loughran and McDonald (2011) in your documentation.
2. Save it here as `LM_MasterDictionary.csv`.
3. Version it with DVC (not Git): `dvc add data/external/LM_MasterDictionary.csv`

Required columns: Word, Negative, Positive, Uncertainty, Litigious.
