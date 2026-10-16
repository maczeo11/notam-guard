# Regulation corpus

Real drone and airspace documents, split into units a citation can point at. It is separate from the small illustrative sample in `data/dgca_car.txt` and `data/notams/`, and the app only uses it when `CORPUS=full` is set (or `python -m src.ingest --regulations` is run). The live demo uses the sample.

| Source | Chunks | What it is |
|---|---|---|
| `drone-rules-2021` | 75 | The Drone Rules, 2021 (G.S.R. 589(E)): all 55 rules and the 5 forms |
| `drone-amendment-rules-2022` | 14 | G.S.R. 108(E), 11 Feb 2022 ("licence" becomes "certificate", registration deadline, form notes) |
| `drone-amendment-rules-2023` | 4 | G.S.R. 715(E), 27 Sep 2023 (identity proof in Form D-4) |
| `utm-policy-framework-2021` | 69 | National UTM Policy Framework, 24 Oct 2021 (a policy, not a rule) |
| `faa-aim-5-1-3-notam` | 14 | FAA AIM 5-1-3: what a NOTAM is and how its fields work. **United States guidance, not Indian law**, and labelled so in every chunk header |

176 chunks, about 14,300 words. `manifest.json` records, per source, the URL, the SHA-256 of the file it was read from, the method, what was left out, and a licence note.

## How accurate is it?

- **The Drone Rules** came from a scan, not a text file. OCR misread clause labels and dropped lines, so the text was **transcribed by reading every page image**, with the OCR as a cross-check. All 55 rules are present and in order, and the figures (heights, distances, weights, periods, fees, the penalty) agree with the OCR reading. The scan is a compiled print hosted on a court website, not the Gazette original, so it has **not been compared word for word with the Gazette**. Check the Gazette before relying on any provision.
- The rules are the **2021 original**. Each rule the 2022 and 2023 amendments changed carries a bracketed *editorial note, not part of the rule* saying what changed.
- The UTM text came from a clean PDF text layer, normalised by script. The FAA text came from HTML.
- This is a study corpus, not legal advice.

## Rebuilding and checking

```
python -m src.regulations build    # rewrite chunks.jsonl from text/ and manifest.json
python -m src.regulations check    # fail if chunks.jsonl is out of date
python -m src.regulations stats    # chunks and words per source
python -m src.regulations eval     # retrieval hit rate on eval_queries.json
```

Chunking follows the documents' own structure: a rule is a chunk, a long rule is cut between sub-rules, a long paragraph between sentences, and every chunk starts with a header naming the document, the Part and the rule. `tests/test_regulations.py` checks the chunker, that all rules and forms exist, that the key figures read correctly, and that `chunks.jsonl` matches a fresh build.

## Retrieval on this corpus

`eval_queries.json` has 18 plain questions, each with the text that should come back. The in-memory keyword search finds the right chunk in its top 3 for **12 of 18 (0.667)**. All six misses are vocabulary gaps (for example "check the airspace map" against a rule that says "verify the digital sky platform"), not errors in the corpus. The project's embedding model (`BAAI/bge-small-en-v1.5`, ranked by cosine similarity the way `PgVectorAdapter` does) finds it for **15 of 18 (0.833)**. It fixes five of the six keyword misses and loses two the keyword search got (the penalty and "What is a NOTAM?" at rank 3). That run used a one-off script that is not kept in this repository, and it has not been run through a live pgvector database.

## Limits

The OCR and normalisation scripts were used once and are not kept in this repository. Source files are not committed (the scans are about 8 MB); their hashes and URLs are in the manifest. The forms are kept as field lists, not layout.
