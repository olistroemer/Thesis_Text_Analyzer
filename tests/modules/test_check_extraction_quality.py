"""Unit tests for mod_check_extraction_quality (SDD §7.1 #2, US-PROF-QUALITY)."""

from pds.core.modules.check_extraction_quality import CheckExtractionQuality

CLEAN_SENTENCE = "the analysis of the data is presented in the following chapter and discussed "
GIBBERISH = "wxq zrtk jvb qpfl mnshg kdwz xbrt "  # no function words


def run_on(build_ctx, text):
    return CheckExtractionQuality().run(build_ctx(raw_text=text))


def test_clean_text_is_ok(build_ctx):
    result = run_on(build_ctx, CLEAN_SENTENCE * 30)  # ~390 tokens, stop-word heavy
    assert result.metrics == {"extraction_quality": "ok"}
    assert result.notes["stop_word_ratio"] > 0.149  # clean cluster per GARBLED_EXTRACTIONS.md


def test_garbled_text_is_flagged(build_ctx):
    result = run_on(build_ctx, GIBBERISH * 50)  # ~300 tokens, no function words
    assert result.metrics == {"extraction_quality": "garbled"}
    assert result.notes["stop_word_ratio"] < 0.10


def test_sparse_text_is_not_judged(build_ctx):
    result = run_on(build_ctx, "drawing label one two")  # poster-style, < 200 tokens
    assert result.metrics == {"extraction_quality": "sparse"}
    assert result.notes["stop_word_ratio"] is None
