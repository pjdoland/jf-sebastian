"""Unit tests for the streaming SentenceChunker (pure text in, chunks out)."""

from jf_sebastian.modules.sentence_chunker import SentenceChunker


def chunk_stream(text, min_words):
    """Feed text word-by-word (like token streaming); return all emitted chunks."""
    c = SentenceChunker(min_words)
    out = []
    for word in text.split():
        out += c.feed(word + " ")
    tail = c.flush()
    if tail:
        out.append(tail)
    return out


def test_groups_sentences_to_min_words():
    out = chunk_stream("One. Two. Three. Four. Five. Six.", 3)
    assert all(len(c.split()) >= 3 for c in out[:-1])      # only the tail may be short
    assert " ".join(out) == "One. Two. Three. Four. Five. Six."


def test_does_not_split_on_abbreviation():
    out = chunk_stream("Hello Dr. Smith is here.", 3)
    assert all(not c.strip().endswith("Dr.") for c in out)
    assert "Hello Dr. Smith is here." in " ".join(out)


def test_soft_cap_flushes_without_terminal_punctuation():
    out = chunk_stream("one two three four five six seven eight nine ten", 3)  # hard cap = 6
    assert len(out) >= 2                                    # streamed, not buffered to the end
    assert out[0] == "one two three four five six"


def test_soft_cap_prefers_a_clause_comma():
    # min_words 3, hard cap 6: should cut at the comma that first reaches 3 words.
    out = chunk_stream("alpha beta gamma, delta epsilon zeta eta", 3)
    assert out[0] == "alpha beta gamma,"


def test_keeps_decimals_intact():
    out = chunk_stream("It costs 3.5 dollars total here.", 3)
    joined = " ".join(out)
    assert "3.5" in joined
    assert all(not c.strip().endswith("3.") for c in out)


def test_decimal_split_across_tokens_is_not_broken():
    # The API streams "1.5" as separate tokens; the period lands at the buffer
    # edge before "5" arrives. The chunker must not treat it as a sentence end.
    c = SentenceChunker(3)
    out = []
    for tok in ["Shake ", "1", ".", "5", " oz ", "rum ", "then ", "strain ",
                "it ", "well", "."]:
        out += c.feed(tok)
    tail = c.flush()
    if tail:
        out.append(tail)
    joined = " ".join(out)
    assert "1.5" in joined          # decimal preserved
    assert "1. 5" not in joined     # not split + rejoined-with-space

    # Same for a leading-dot decimal (".5 oz") arriving as "." then "5".
    c2 = SentenceChunker(3)
    out2 = []
    for tok in ["Add ", ".", "5", " oz ", "lime ", "juice ", "to ", "it ",
                "now", "."]:
        out2 += c2.feed(tok)
    tail2 = c2.flush()
    if tail2:
        out2.append(tail2)
    assert ".5 oz" in " ".join(out2)


def test_flush_returns_none_when_empty():
    assert SentenceChunker(3).flush() is None


def test_no_chunk_until_min_words_then_flush():
    c = SentenceChunker(5)
    assert c.feed("Short. ") == []        # 1 word, below the threshold
    assert c.flush() == "Short."
