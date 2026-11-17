---
title: "Thesis Text Analyzer — Limitations and Biases of the Bundled NLP Components"
subtitle: "What punkt, langdetect and Flesch/Amstad get wrong, and where results need caution"
status: "Current as of 2026-08-26 (issue #43)"
---

# Limitations and Biases of the Bundled NLP Components

## 1. Scope

**The MVP contains no language model.** Nothing here is an LLM, a neural network, or a classifier
trained on AI-generated text. The pipeline is deterministic arithmetic over token counts, with
exactly three exceptions where a *trained or corpus-derived* component makes a judgement:

| Component | Kind | Used by | Decides |
|---|---|---|---|
| NLTK **punkt** (`punkt_tab`) | Unsupervised statistical sentence-boundary model, pretrained on newspaper corpora | `mod_tokenize` | Where sentences end, and hence every word- and sentence-level metric |
| **langdetect** | Naive Bayes over character n-gram profiles, trained on Wikipedia | `mod_classify_language` | The document language, which gates tokenisation and readability entirely |
| **Flesch / Amstad** via textstat, CMUdict and Pyphen | Fixed linear formulas over a syllable *heuristic* | `mod_readability` | `flesch_reading_ease` |

Everything downstream (`mod_surface_counts`, `mod_vocabulary`, `mod_redundancy`) is stdlib
arithmetic — but arithmetic *over punkt's output*, so punkt's errors propagate into all of it. The
inventory of what these components are and how they are licensed is
[`dependencies.md`](dependencies.md); this page is about whether to trust their numbers.

**Why this page exists.** The research question is whether AI influence on student writing is
visible in text metrics over publication years (SDD §2.1). Every claim of that shape is a claim
about *differences between cohorts*. A measurement error that is constant across cohorts is
harmless; one that *correlates with time, language, subject, or PDF toolchain* manufactures the
finding. Each section below therefore says what the error does to a *comparison*, not just to a
number. Being explicit about this is also a QA-GDPR / US-ALL-PRIVACY obligation: the tool should
tell its users what it cannot know.

All the concrete misbehaviour below was **reproduced against the installed versions** (nltk 3.9.4,
langdetect 1.0.9, textstat 0.7.13, pyphen 0.17.2), not inferred from documentation. Verification
snippets are in [§9](#9-reproducing-the-examples).

---

## 2. NLTK punkt — sentence segmentation

### 2.1 What it actually is

Punkt [Kiss & Strunk 2006] is *unsupervised*: given raw text it learns which tokens are
abbreviations, which are sentence-initial, and which collocations straddle a period, then uses those
statistics to decide whether each `.` `!` `?` ends a sentence. Its strength is needing no
annotation. Its weakness is that all of that learning happened **on the training corpus** —
`nltk.sent_tokenize` loads a *pretrained* model and learns nothing from the thesis in front of it.

### 2.2 Provenance of the two models we load

`mod_tokenize` loads exactly two of the 19 bundled models
(`NLTK_LANGUAGES = {"en": "english", "de": "german"}`). From the `punkt_tab` README:

| Model | Trained on | Training size | Consequences |
|---|---|---|---|
| `english` | Wall Street Journal, Penn Treebank (LDC) | ~469,000 tokens | American newspaper prose, ca. 1990. No academic register, no citations, no formulas, no enumerated headings. |
| `german` | Neue Zürcher Zeitung CD-ROM | ~847,000 tokens | **Swiss** German newspaper prose, and the README notes the corpus "uses `ss` instead of `ß`" — so the model never saw `ß` in training, in a tool whose main target is theses written in German-German orthography. |

The segmentation of a 2026 German master's thesis is therefore decided by statistics from a 1990s
Swiss newspaper. That is the largest domain gap in the pipeline.

### 2.3 Verified failure modes

Every example is real output from `nltk.sent_tokenize` on the installed model.

**Over-splitting on abbreviations and numbered references** — the dominant error in academic prose,
because the abbreviations theses use constantly are rare in newspapers:

| Input | True | punkt |
|---|---|---|
| `Siehe Abb. 3.2 sowie Tab. 4. Die Werte steigen.` | 2 | **4** — `['Siehe Abb.', '3.2 sowie Tab.', '4.', 'Die Werte steigen.']` |
| `See e.g. Smith et al. (2020, p. 12). The result is clear.` | 2 | **4** — `['See e.g.', 'Smith et al.', '(2020, p. 12).', 'The result is clear.']` |
| `Das ist z.B. deutlich schneller als u.a. bei Schmidt et al. (2020).` | 1 | **2** — the parenthetical citation becomes its own "sentence" |

Note the asymmetry: `Vgl.` and `ff.` are handled, `Abb.` and `Tab.` are not. Which abbreviations
survive is an accident of what appeared in the training newspaper, so the error is **not uniform
across writing styles** — a thesis that references figures often is penalised more than one that
does not.

**Bibliographies are catastrophic.** Author initials plus year-in-parentheses look exactly like
sentence boundaries:

```
Mueller, J. R. (2019). Titel der Arbeit. Verlag.
Schmidt, A. B. (2020). Anderer Titel. Verlag.
```

punkt returns **9 "sentences"** for those two reference entries: `['Mueller, J. R.', '(2019).',
'Titel der Arbeit.', 'Verlag.', 'Schmidt, A.', 'B.', '(2020).', 'Anderer Titel.', 'Verlag.']`.
That is roughly 4–5 pseudo-sentences per entry, all of them 1–4 words long, so a bibliography's
contribution to `sentence_count` is wildly out of proportion to its share of the text. It drags
`avg_sentence_len` down and `std_sentence_len` up **in proportion to how many references a thesis
has** — i.e. it correlates with the very scholarly diligence the study might want to measure. The
size of the effect on a real corpus has not been measured; measuring it (the reference section's
share of `sentence_count`) is a cheap and worthwhile check before publishing anything about
sentence length.

**Under-splitting on headings.** Headings carry no terminal punctuation, so they fuse into the
following body sentence:

```
'2 Grundlagen\n2.1 Motivation\nIn diesem Kapitel wird die Fragestellung erlaeutert.'
-> 1 sentence
```

Every heading silently lengthens one sentence. LaTeX-heavy theses with many subsection headings are
affected more than Word documents with fewer.

**Line-break hyphenation survives as a broken token.** `'Die Unter-\nsuchung zeigt einen Effekt.'`
stays one sentence (correct) but yields the word tokens `Unter-` and `suchung` where there was one
word. That inflates `word_count`, deflates `avg_word_len`, and injects spurious hapax legomena,
polluting `hapax_token_ratio`, `hapax_type_ratio`, `ttr`, and `yules_k`. Whether it happens at all
depends on the *PDF producer*, not the writing: a LaTeX/pdfTeX document with justified text
hyphenates far more than a Word document. **This is a producer-correlated bias, and
`producer_category` is one of the metrics** — treat any correlation between a vocabulary metric and
`producer_category` as suspect until this is ruled out.

### 2.4 Word tokenisation is English regardless of language

`nltk.word_tokenize(sentence, language="german")` passes `language` only to the *sentence*
tokenizer. The words themselves come from `_treebank_word_tokenizer`, a Penn-Treebank tokenizer with
**English** rules (`nltk/tokenize/__init__.py`, `word_tokenize` lines 83–86). For German:

- English clitic rules fire where they should not, and German ones do not exist: no splitting of
  `zum`/`ins`/`aufs`, and compounds such as `Datenschutzgrundverordnung` stay single tokens — which
  is arguably right, but it makes German `avg_word_len` and `ttr` **structurally incomparable** to
  English values from the same tool. Never compare a German and an English thesis on
  `avg_word_len`, `ttr`, or `root_ttr`; compare within a language.
- Quotation handling is tuned for `"` and `'`, not for German `„ “` or `» «`.

Minor and harmless, for completeness: because `preserve_line` defaults to `False`, calling
`word_tokenize` on an already-split sentence re-runs punkt on it. The extra split is discarded (only
tokens are kept), so no metric changes — wasted work, not an error.

### 2.5 Effect on metrics

| Metric | Direction of punkt error | Correlates with |
|---|---|---|
| `sentence_count` | **Over-counted** (abbreviations, bibliography) | citation density, figure/table references |
| `avg_sentence_len` | **Under-estimated**, sometimes by 30%+ | same |
| `std_sentence_len` | **Inflated** (many 1–3-word pseudo-sentences) | same |
| `word_count`, `avg_word_len` | Distorted by line-break hyphenation | PDF producer |
| `ttr`, `root_ttr`, hapax ratios, `yules_k` | Spurious types from broken words | PDF producer |
| `bigram_/trigram_repetition_rate` | n-grams do not cross sentence boundaries, so over-splitting **removes** legitimate n-grams and lowers measured repetition | citation density |

---

## 3. langdetect — language classification

### 3.1 What it actually is

A Python port of Nakatani Shuyo's `language-detection`: naive Bayes over character 1–3-grams against
**55 fixed language profiles built from Wikipedia**. It is not a model of academic German or
academic English; it is a model of Wikipedia German and Wikipedia English.

Two properties of the implementation matter more than the algorithm:

- **It is randomised.** `Detector` runs `n_trial = 7` independent trials, each with a randomly
  perturbed prior (`ALPHA_DEFAULT = 0.5`, `ALPHA_WIDTH = 0.05`) over a random sample of the text's
  n-grams, then averages the per-trial posteriors.
- **It truncates hard.** `Detector.max_text_length = 10000` — langdetect reads the first ~10,000
  characters and discards the rest. `mod_classify_language` already slices `text[:20_000]`, so the
  effective decision window is the **first ~10,000 characters**: title page, front matter,
  abstract(s), and the start of the table of contents. **The body of the thesis is never read.**

### 3.2 The seed makes it reproducible, not meaningful

`mod_classify_language` sets `DetectorFactory.seed = 0`, so identical input gives identical output
(QA-REPRO, QA-TEST). That is correct and necessary. It does **not** make the answer stable in any
deeper sense — it fixes *one* draw from a distribution. On the same 292-character bilingual
abstract, changing only the seed:

| `DetectorFactory.seed` | Result |
|---|---|
| 0 (**what we ship**) | `en: 0.857`, `de: 0.143` |
| 1 | `en: 1.000` |
| 2 | `en: 0.714`, `de: 0.286` |
| 42 | `en: 1.000` |
| 1234 | `en: 0.571`, `de: 0.429` |

The *label* was stable here; the **confidence swung from 0.571 to 1.000**. Read
`language_confidence` accordingly.

### 3.3 `language_confidence` is not a probability

Because the posterior is the mean of 7 trial outcomes, when the trials disagree the value can only
land on a multiple of 1/7 — 0.143, 0.286, 0.429, 0.571, 0.714, 0.857 — and when all 7 agree it
saturates just below 1.0 (observed 0.9999966 … 0.9999982). Every value in the table above is one of
those. So:

- It is effectively a **7-step ordinal** ("how many of 7 trials agreed"), not a calibrated
  probability. Do not average it, do not threshold it at 0.95, do not feed it to anything that
  assumes a probability scale. Treat `≈1.0` as "unanimous" and anything lower as "the detector was
  unsure", and nothing finer.
- Rounding to 4 decimals preserves the artefact, so `0.8571` in the database means "6 of 7 trials".

### 3.4 The bilingual-front-matter trap

German theses conventionally carry **both** an English `Abstract` and a German `Zusammenfassung`, in
exactly the region langdetect reads. Verified:

```
"Abstract\nThis thesis investigates the impact of large language models on academic
 writing. We present a set of text metrics ...\nZusammenfassung\nDiese Arbeit
 untersucht die Auswirkungen grosser Sprachmodelle ..."
-> en: 0.857, de: 0.143
```

A German thesis classified `en`. This is the **highest-consequence failure in the pipeline**,
because `language_code` is not merely a metric — it *gates* two modules:

- `mod_tokenize` loads the wrong punkt model (English statistics on German text);
- `mod_readability` applies **Flesch's English coefficients to German text**, which is not a small
  error: Flesch is `206.835 − 1.015·ASL − 84.6·ASW`, Amstad is `180 − ASL − 58.5·ASW`. German words
  carry more syllables, so scoring German with the English syllable weight produces a heavily
  negative, meaningless number that is nonetheless stored as a valid metric and plotted.

There is no in-pipeline detector for this. **Practical guardrail:** before drawing conclusions,
group the corpus by `language_code` and check the split against expectation for the institution. A
cohort that is 30% `en` at a German university is a red flag about the *detector*, not about the
students. Repositories with a bilingual-abstract house style are disproportionately mislabelled — an
institution-correlated bias, not a random one.

### 3.5 It never says "I don't know"

Only 55 languages exist to langdetect, and it always returns the best of them. Verified on
formula-and-citation soup, 78 characters:

```
"f(x) = ax^2 + bx + c , cf. Eq. (3.2); see [12], [13]. R^2 = 0.94 , p < 0.001 ."
-> so: 0.429, en: 0.429, ca: 0.143      # "so" = Somali
```

Related limits:

- **Short text.** `MIN_CHARS = 200` (SDD §7.2) keeps the worst cases out as `na`, but 200 characters
  is a low bar. Poster-style or heavily garbled documents pass it and get a confident wrong answer.
- **Garbled extractions.** A PDF with a broken `/ToUnicode` CMap extracts as gibberish, which still
  has a character distribution, so langdetect classifies it happily. `extraction_quality` flags this
  but does not block anything (SDD §7.4), so `language_code` on a `garbled` row is noise. **Always
  filter on `extraction_quality = 'ok'` before analysing language-derived metrics.**
- **Code-switching.** No mixed-language handling exists; the answer is one label per document. A
  German thesis with English-heavy method chapters drifts toward `en` with no signal that the
  document is mixed.
- **Locale granularity.** Output is coarse (`de`, `en`), with only `zh-cn`/`zh-tw` distinguished.
  Austrian, Swiss and German German are one label — see [§4.2](#42-the-dialect-nobody-chose) for why
  that matters downstream.

---

## 4. Flesch / Amstad readability

`mod_readability` produces the single metric `flesch_reading_ease`, for `en` and `de` only; every
other language is `na` (SDD §7.2). The coefficients textstat actually uses, read from
`textstat.backend.utils.constants.LANG_CONFIGS`:

| Language | Formula | Coefficients as shipped |
|---|---|---|
| `en` | Flesch Reading Ease [Flesch 1948] | `206.835 − 1.015·ASL − 84.6·ASW` |
| `de` | Amstad's *Verständlichkeitsindex* [Amstad 1978] | `180 − 1·ASL − 58.5·ASW` |

`ASL` = average sentence length in words, `ASW` = average syllables per word. Both inputs are
estimated, and both estimates are wrong in specific, non-cancelling ways.

### 4.1 English syllables need CMUdict, which is now bundled (was a live defect)

`textstat.backend.counts.count_syllables` looks each word up in the **CMU Pronouncing Dictionary**
(127,069 entries; it counts stressed vowel phonemes) and falls back to Pyphen hyphenation only for
words CMUdict does not know. textstat's loader is:

```python
try:
    nltk.data.find("corpora/cmudict")
except LookupError:
    nltk.download('cmudict', quiet=True)
```

That auto-download was a live defect until **#75**: `packaging/tta.spec` bundled only
`punkt_tab`, so the app reached out to `raw.githubusercontent.com` on the first English thesis
(contradicting US-ALL-OFFLINE and QA-PRIV), and with the network blocked `mod_readability` errored
on **every** English thesis. This audit found it independently as finding **F7** in
[`dependencies.md`](dependencies.md) §8; CI found it the same week, because the `tta doctor`
offline self-check refuses to let a probe open a socket.

**Fixed, and the fix does not rely on the corpus being present.** `cmudict` is now bundled beside
`punkt_tab`, and both CI jobs fetch both. Independently of that, `mod_readability` neuters
`nltk.download` for the duration of the textstat call, so **no outbound attempt is possible** even
on a from-source machine that lacks the corpus; the resulting `LookupError` is converted into an
error naming `cmudict` and how to obtain it. German never touches CMUdict and computes either way.

What that leaves for research validity is *better* than the old comparability worry, not merely
different: a run either has CMUdict — every frozen binary does — or it fails loudly. There is no
longer a silent path where English syllables are counted by a different method (§4.3) without the
operator knowing. The remaining caveat is the ordinary one: English and German syllable counts come
from different machinery, so cross-language readability comparison stays invalid (§4.3, §5).

### 4.2 The dialect nobody chose

textstat calls `Pyphen(lang=lang)` with the bare code from `mod_classify_language`. Pyphen builds
its language map by iterating `sorted(dictionaries.iterdir())` and binding each short code to the
**first** regional variant it meets. Verified:

| Requested | Dictionary actually loaded |
|---|---|
| `"de"` | `hyph_de_AT.dic` — **Austrian** German |
| `"en"` | `hyph_en_GB.dic` — **British** English |

Nobody chose this: `AT` sorts before `CH` and `DE`, `GB` before `US`. Combined with §2.2, the
pipeline models **Swiss** German for sentences and **Austrian** German for syllables, and
**American** English for sentences and **British** English for syllables.

How much it matters, measured:

- **German: not at all in practice.** `de_AT`, `de_CH` and `de_DE` all derive from the same
  `dehyphn.tex` patterns and returned identical syllable counts on all test words
  (`Bachelorarbeit`, `Untersuchung`, `Datenschutzgrundverordnung`, …). Worth documenting, not worth
  fixing.
- **English: it matters, precisely where it hurts.** `en_GB` and `en_US` disagree on `every`
  (1 vs 2), `hierarchical` (4 vs 5), `evaluation` (3 vs 4), `tokenisation` (3 vs 4). Pyphen only
  fires for words CMUdict lacks — technical jargon, neologisms, non-English proper nouns — which is
  exactly the vocabulary that distinguishes one CS thesis from another. The dialect accident
  therefore concentrates its effect on the domain-specific vocabulary instead of averaging out.

### 4.3 Hyphenation points are not syllables

Pyphen returns *legal line-break positions*, which is a different thing from a syllable count, and
it is deliberately conservative: `LEFTHYPHENMIN`/`RIGHTHYPHENMIN` forbid breaks near word edges
(`left=2, right=2` by default in `Pyphen.__init__`; `RIGHTHYPHENMIN 3` in `hyph_en_US.dic`).

**German: a systematic over-count, on exactly the words this corpus is full of.** Across 16 test
words the estimate was never too low and was too high 6 times. The cause is visible in the
hyphenation string: at a *compound seam* the dictionary's COMPOUND feature and its pattern rules
both fire, emitting a single-letter fragment that is then counted as a syllable. Every `X-arbeit`
compound is affected:

| Word | Pyphen hyphenation | Pyphen | Actual | Error |
|---|---|---|---|---|
| `arbeit` | `ar-beit` | 2 | 2 | 0 — the bare word is fine |
| `bachelorarbeit` | `ba-che-lor-a-r-beit` | 6 | 5 | **+1** |
| `masterarbeit` | `mas-ter-a-r-beit` | 5 | 4 | **+1** |
| `abschlussarbeit` | `ab-schluss-a-r-beit` | 5 | 4 | **+1** |
| `diplomarbeit` | `di-plom-a-r-beit` | 5 | 4 | **+1** |
| `hausarbeit`, `facharbeit`, `teamarbeit` | `haus-a-r-beit`, … | 4 | 3 | **+1** |
| `projektarbeit`, `seminararbeit` | `pro-jekt-a-r-beit`, … | 5, 6 | 4, 5 | **+1** |

`Bachelorarbeit`, `Masterarbeit` and `Abschlussarbeit` are among the most frequent content words in
this exact corpus — they sit on the title page, in the declaration of authorship, and throughout the
introduction. The same artefact appears in other compounds (`hyperparameteroptimierung` →
`hy-per-pa-ra-me-te-r-opti-mie-rung`, where the count happens to come out right while the
boundaries are wrong). Because the error is **one-directional**, it does not cancel across a
document: German `ASW` is biased upward, German theses are systematically scored as *harder* than
they are, and the size of the bias tracks how nominally compounded the writing is — a register
difference, not a comprehension difference.

**English: only for words CMUdict does not know.** CMUdict counts stressed vowel phonemes and is
reliable. On the Pyphen fallback path the errors run the other way — no legal break point at all
means one syllable:

| Word | Pyphen (`en_GB`) | Actual |
|---|---|---|
| `idea` | 1 | 3 |
| `area` | 1 | 3 |
| `every` | 1 (`en_GB`) / 2 (`en_US`) | 2 |

`idea` and `area` *are* in CMUdict, so those particular values only surface when CMUdict is missing
(§4.1) — which is the state the shipped binary is in today. The words that take the Pyphen path even
with CMUdict present are technical jargon and proper nouns (§4.2).

### 4.4 The Flesch score is computed on a different segmentation than the grid shows

This is the caveat most likely to produce a false conclusion. `flesch_reading_ease` does **not** use
punkt. textstat counts sentences with a regex and discards short ones:

```python
sentences = re.findall(r"\b[^.!?]+[.!?]*", text, re.UNICODE)   # then: drop sentences of <= 2 words
```

and counts words by whitespace-splitting after punctuation removal. On the same text:

| Same paragraph, 5 real German sentences | punkt (→ the grid) | textstat (→ inside Flesch) |
|---|---|---|
| sentences | 8 | 7 |
| word tokens | 35 (letters-only rule) | 40 |
| average sentence length | **4.38** | **5.71** |

A **30% divergence** on one paragraph. Consequences:

- `avg_sentence_len` in the grid is **not** the `ASL` inside `flesch_reading_ease`. They are two
  different measurements of the same concept and they disagree. Never explain a movement in
  `flesch_reading_ease` by pointing at `avg_sentence_len`, and never regress one on the other as
  though they were independent.
- `word_count` differs too. `_tokens.is_word` requires at least one letter, so `3.14` and `[12]` are
  excluded from the grid's `word_count`; textstat strips punctuation first and therefore counts them
  — `'The mean was 3.14 s and R^2 = 0.94 , see [12].'` becomes the ten "words"
  `['The','mean','was','314','s','and','R2','094','see','12']` and **three** "sentences".
  Formula- and table-heavy theses diverge the most.
- The `<= 2 words` rule discards headings and short list items from the Flesch computation but not
  from the grid metrics, so the two disagree *more* on heavily structured documents.

### 4.5 The formulas were never validated for this

Even with perfect inputs the output would need caution:

- **Flesch (1948)** was calibrated against comprehension tests on American school texts and adult
  magazine prose, and the 0–100 "reading ease" band was designed for that material. Academic prose
  sits off the bottom of the scale; scores are routinely negative and the published labels
  ("difficult", "college level") do not extend there. The number is usable as an **ordinal**
  comparison within a corpus; the absolute value and its verbal band are not meaningful for theses.
- **Amstad (1978)** re-fitted Flesch's constants for German on 1970s Swiss newspaper material. It
  inherits every assumption and adds a second layer of domain mismatch. Interpretation guidance for
  German academic text does not exist in the literature.
- **Both are proxies, not measurements.** Word and sentence length correlate with difficulty in some
  genres; they do not measure comprehensibility. Bailin & Grafstein (2001) show the underlying
  linguistic assumptions do not hold generally — syntactic complexity, cohesion and terminology load
  are all invisible to the formulas. A thesis can shorten its sentences, keep every piece of
  impenetrable jargon, and "improve" its score.
- **Arithmetically linear, interpretively not.** The formula is linear in `ASL` and `ASW`, so
  differences are well defined *as formula output*. The mapping to comprehension is neither linear
  nor calibrated outside the original band, so a 10-point gap at −40 is not the same thing as a
  10-point gap at 60, and ratios are meaningless. Report distributions and ranks within a corpus.

### 4.6 Formulas, tables and references contaminate the input

`mod_readability` runs on the whole extracted text — bibliography, table contents, page headers
and footers, table of contents included. Those regions have extreme word and "sentence"
lengths and are counted at full weight. A thesis with 40 pages of appendix tables is partly
measuring its tables. This affects theses unevenly by discipline and by whether the appendix was in
the PDF at all, which makes it a subject-area-correlated bias.

Since #22 the text metrics read `prose_text`, from which code (monospaced spans) and math
(math-font spans) are removed ([§5](#5-adjacent-corpus-derived-heuristics), SDD §7.4). That takes
out most formula fragments and code listings, but **not** tables, tables of contents, headers and
footers or the bibliography; in Exp #22 table regions alone held ~10 % of all characters. A line
heuristic for them is a separate experiment (#97).

---

## 5. Adjacent corpus-derived heuristics

Not "models", but also judgements learned from a corpus, carrying the same kind of bias. Brief,
since they belong to their own tickets:

- **The font filter of `mod_extract_pymupdf`** ("font filter v1", #22, SDD §7.4) decides what is
  code or math from the **font** a span is set in, not from its content: monospaced fonts count as
  code, a name list of math fonts as math. It inherits the blind spots of that proxy:
  - *Missed:* code set in a proportional font (a listing in Arial, a screenshot-like box in the body
    font), math typed as ordinary characters in the body font (`x = 2y + 1` in Word without the
    equation editor, digits and operators that TeX takes from the roman font: `O(g^4)` keeps
    `(4)`), math in fonts outside the list. All of it stays in `prose_text`.
  - *Over-removed:* everything in a monospaced font, including URLs and DOIs that LaTeX's `\url`
    sets in a typewriter font (mostly bibliography), file names and command names in running text.
    Isolated punctuation and slashes in a math font disappear too (`AdS3/CFT2` loses the `/`).
  - *Whole-document false positives:* a thesis set **entirely** in a monospaced font, or a Word
    document whose body text is set in **Cambria Math**, loses nearly all of its prose. In the
    Exp #22 corpus that was 2 of 3,233 theses (93 % Courier New, 96 % Cambria Math); 5 lost more
    than half. `prose_text` can then be empty, which makes tokenisation and everything after it
    `na`. The two counts `removed_monospace_chars` / `removed_math_chars` make such theses visible:
    compare them with `text_chars`.
  - Text the PDF stores as a picture (formula images, Type3 bitmap fonts) is not text at all and is
    never seen by the filter.
- **`mod_check_extraction_quality`** thresholds the ratio of common English/German function words at
  `0.10`, a value derived from the exploration corpus (`harvester/GARBLED_EXTRACTIONS.md`). It is
  therefore **English/German-specific**: a clean thesis in another language looks garbled. It also
  needs ≥ 200 word tokens to judge at all, so genuinely short documents come back unjudged rather
  than flagged.
- **`mod_classify_thesis_type`** ([ADR-0019](adr/0019-thesis-type-by-detection.md)) is a title-page
  keyword heuristic over German and English degree terms. It returns `unspecified` rather than `na`
  when it finds nothing, so `unspecified` conflates "no keyword on the title page", "title page not
  extracted", and "an institution that words its title pages differently". Do not read
  `unspecified` as a property of the thesis.
- **`mod_determine_publication_year`** prefers the title-page year, then PDF `creation_year`, then
  `modification_year`. The PDF fallbacks are **not** publication dates: a thesis re-saved or
  re-exported years later carries the later date. Since the whole research question is a trend over
  publication year, **always check `publication_year_source`** before plotting — a cohort whose
  years come mostly from `pdf_modification` cannot support a temporal claim.

---

## 6. What this means for the research question

Ranked by how likely each is to fabricate a trend over publication year:

1. **PDF producer drift.** LaTeX and Word versions, and their hyphenation and font-encoding
   behaviour, change over the years a corpus spans. Producer-correlated tokenisation errors (§2.3)
   therefore produce apparent time trends in vocabulary metrics with no change in writing at all.
   Cross-check every temporal finding against `producer_category`.
2. **Extraction-quality drift.** Older PDFs are likelier to have broken CMaps, and `garbled` rows
   keep producing metrics. Filter on `extraction_quality = 'ok'`.
3. **Language misclassification** (§3.4) — institution- and house-style-correlated, not random.
4. **Length confounds.** `ttr` and `hapax_token_ratio` are strongly length-dependent by
   construction; `root_ttr` and `yules_k` much less so. Thesis length varies with degree type and
   discipline, so any comparison must control for length or be restricted to the length-stable
   metrics. This is why both hapax variants ship (SDD §7.1) rather than one being chosen up front.
5. **Date provenance** (§5) — a trend over a year that came from a file timestamp is not a trend.

None of this argues against the metrics. It argues for reporting **within-language,
within-`extraction_quality`, length-controlled, producer-checked** comparisons, and for saying so in
any publication.

---

## 7. Quick reference: when to distrust a metric

| Metric | Distrust when | Because |
|---|---|---|
| `language_code`, `language_confidence` | front matter is bilingual; `extraction_quality != 'ok'`; text near 200 chars; confidence below ~1.0 | §3.2–§3.5; the effective window is the first ~10k chars |
| `sentence_count`, `avg_sentence_len`, `std_sentence_len` | citation-dense or bibliography-heavy text; many headings | §2.3 |
| `word_count`, `char_count_alpha`, `avg_word_len` | `producer_category` suggests justified LaTeX output | §2.3, line-break hyphenation |
| `ttr`, `root_ttr`, `hapax_token_ratio`, `hapax_type_ratio`, `yules_k` | comparing across languages, lengths, or producers | §2.4, §2.5, §6 item 4 |
| `bigram_/trigram_repetition_rate` | comparing citation-dense with citation-light theses | §2.5 — over-splitting removes n-grams |
| `flesch_reading_ease` | always, for the absolute value; English on a machine without CMUdict; any German document whose `language_code` might be wrong | §4.1–§4.5 |
| `extraction_quality` | the document is neither English nor German, or is very short | §5 |
| `text_chars` and every text metric | `removed_monospace_chars` or `removed_math_chars` is a large part of `text_chars` (the font filter may have removed body text) | §5, font filter |
| `removed_monospace_chars`, `removed_math_chars` | reading them as exact code/formula volume | §5 — font-based proxy; URLs count as code, math in the body font is missed |
| `thesis_type` = `unspecified` | reading it as a fact about the thesis | §5 |
| `publication_year` | `publication_year_source != 'title_page'` | §5 |

---

## 8. What would reduce these (options, not commitments)

Recorded so the trade-offs are not re-derived later. None is an MVP commitment.

| Limitation | Cheapest real improvement | Cost |
|---|---|---|
| CMUdict missing (§4.1) | Bundle it in `packaging/tta.spec`; add it to the CI `nltk.downloader` line | Small, and it closes an offline-promise hole (#4) |
| Bilingual front matter flips the language (§3.4) | Detect on a *body* window (skip the first N pages) instead of the head, or aggregate per-page votes | Moderate; needs a page-aware `raw_text` |
| Bibliography wrecks sentence stats (§2.3) | Detect and exclude the reference section before tokenising | Moderate; heuristic, own module |
| punkt's newspaper abbreviations (§2.3) | Extend the loaded model's `abbrev_types` with an academic list (`Abb.`, `Tab.`, `Kap.`, `vgl.`, `Fig.`, `cf.`, `resp.`), or re-train punkt per document | Small to moderate; bumps `mod_tokenize`'s version, so re-runs are needed |
| Pyphen dialect accident (§4.2) | Pass `en_US`/`de_DE` explicitly instead of the bare code | Trivial, but the call lives in textstat, not in our code |
| German compound over-count (§4.3) | Discard single-letter fragments before counting, or count syllables from vowel groups instead of hyphenation points | Small, but means computing syllables ourselves |
| Flesch/ASL mismatch (§4.4) | Compute Flesch from *our* punkt sentences and our own syllable counts instead of calling textstat | Moderate; drops a dependency, gains internal consistency |
| All of the above, upstream | The library-comparison study for the extraction layer (SDD §2.1.1) | Already planned |

---

## 9. Reproducing the examples

```bash
# punkt over- and under-splitting (Sec. 2.3)
python -c "
import nltk
for t in ['Siehe Abb. 3.2 sowie Tab. 4. Die Werte steigen.',
          'Mueller, J. R. (2019). Titel der Arbeit. Verlag.\nSchmidt, A. B. (2020). Anderer Titel. Verlag.',
          '2 Grundlagen\n2.1 Motivation\nIn diesem Kapitel wird die Frage erlaeutert.']:
    print(len(nltk.sent_tokenize(t, language='german')), nltk.sent_tokenize(t, language='german'))
"

# langdetect: seed sensitivity and the bilingual trap (Sec. 3.2-3.4)
python -c "
from langdetect import DetectorFactory, detect_langs
t = ('Abstract\nThis thesis investigates the impact of large language models on academic writing. '
     'We present a set of text metrics and evaluate them empirically on a corpus of theses.\n'
     'Zusammenfassung\nDiese Arbeit untersucht die Auswirkungen grosser Sprachmodelle auf das '
     'wissenschaftliche Schreiben.')   # exactly the 292 chars used in Sec. 3.2/3.4
for s in (0, 1, 2, 42, 1234):
    DetectorFactory.seed = s; print(s, detect_langs(t))
"

# Pyphen: which dictionary a bare code resolves to (Sec. 4.2)
python -c "import pyphen; print(pyphen.LANGUAGES['de'], pyphen.LANGUAGES['en'])"

# Pyphen: the compound-seam over-count (Sec. 4.3)
python -c "
import pyphen; p = pyphen.Pyphen(lang='de_AT'); q = pyphen.Pyphen(lang='en_GB')
for w in ['arbeit','bachelorarbeit','masterarbeit','abschlussarbeit','hausarbeit']:
    print(w, p.inserted(w), len(p.positions(w))+1)
for w in ['idea','area','every']: print(w, q.inserted(w), len(q.positions(w))+1)
"

# punkt vs textstat segmentation on one paragraph (Sec. 4.4)
python -c "
import nltk
from textstat.backend import counts
t = ('Diese Arbeit untersucht die Auswirkungen grosser Sprachmodelle auf das wissenschaftliche '
     'Schreiben. Siehe Abb. 3.2 sowie Tab. 4. Vgl. dazu Mueller (2019, S. 23 ff.). Die Werte '
     'steigen deutlich an. Das Ergebnis ist z.B. bei Schmidt et al. (2020) ebenfalls dokumentiert.')
s = nltk.sent_tokenize(t, language='german')
w = sum(1 for x in s for k in nltk.word_tokenize(x, language='german') if any(c.isalpha() for c in k))
print('punkt:', len(s), 'sentences,', w, 'words, ASL', round(w/len(s), 2))
print('textstat:', counts.count_sentences(t), 'sentences,', counts.count_words(t), 'words, ASL',
      round(counts.count_words(t)/counts.count_sentences(t), 2))
"

# CMUdict absence, i.e. what the frozen binary actually faces (Sec. 4.1)
#   1. mkdir -p /tmp/nd/tokenizers
#      cp -r "$(python -c 'import nltk; print(nltk.data.find("tokenizers/punkt_tab"))')" /tmp/nd/tokenizers/
#   2. NLTK_DATA=/tmp/nd python -c "
#        import nltk; nltk.data.path = ['/tmp/nd']
#        import textstat; textstat.set_lang('en')
#        print(textstat.flesch_reading_ease('This is a short English paragraph. It has sentences.'))"
#      -> downloads cmudict if online; raises LookupError if not.
```

---

## 10. Extension trigger

If a **local model** is ever added — the subject-area classifier (#44) or any of the LM-based modules
in SDD §12 — this page must gain a section for it *before* that module ships, covering at minimum:
training data and its provenance, known demographic and topical biases, calibration of any
confidence it reports, determinism under a fixed seed, and behaviour on out-of-distribution input
(garbled text, the wrong language, very short documents). The licence side of the same addition
belongs in [`dependencies.md`](dependencies.md) §10 — model weights are licensed separately from
inference code, and several common model licences impose field-of-use restrictions that
GPL-3.0-or-later cannot accept.

**References:** [Flesch 1948], [Amstad 1978], [Kiss & Strunk 2006], [Cavnar & Trenkle 1994],
[Bailin & Grafstein 2001], [Yule 1944] — see [`references.bib`](references.bib).
