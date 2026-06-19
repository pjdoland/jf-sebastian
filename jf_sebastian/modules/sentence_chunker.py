"""
Streaming sentence chunker.

Accumulates streamed LLM tokens and emits speakable chunks: groups of one or
more complete sentences totaling at least `min_words`, split on sentence
boundaries. It is abbreviation-aware (so "Dr." does not split a chunk early)
and has a soft cap that flushes at a clause when no sentence boundary arrives
(so a run-on or a response with no terminal punctuation still streams instead
of buffering to the very end).

Pure text-in / chunks-out, with no OpenAI or network dependency, so it can be
tested in isolation.
"""

import re

# A sentence boundary is . ! or ? with a non-space char before it and real
# whitespace after it. The trailing-whitespace requirement (not end-of-string)
# is important while streaming: a period sitting at the current buffer's edge may
# be a decimal mid-number ("1.5" arriving as "1." then "5"), so we defer it to
# the next token or to flush() instead of splitting it. The lookbehind avoids
# floating punctuation; the lookahead keeps decimals like "3.5" intact too (that
# dot is followed by a digit, not whitespace).
SENTENCE_END_PATTERN = re.compile(r'(?<=\S)[.!?]+(?=\s)')
# Fallback split point for the soft cap: a comma followed by whitespace.
CLAUSE_END_PATTERN = re.compile(r',(?=\s)')

# Tokens whose trailing period is usually an abbreviation, not a sentence end.
# Lets "Hello Dr." keep accumulating instead of splitting after "Dr."
_ABBREVIATIONS = frozenset({
    "dr", "mr", "mrs", "ms", "sr", "jr", "st", "mt", "rev", "gen", "sen", "gov",
    "prof", "capt", "lt", "col", "vs", "etc", "no", "fig", "approx", "dept",
    "e.g", "i.e", "a.m", "p.m", "u.s", "u.k", "ph.d",
})


def _ends_with_abbreviation(text: str) -> bool:
    """True if text's last whitespace-token is a known abbreviation (so a period
    right after it is not a real sentence boundary)."""
    last = text.rsplit(maxsplit=1)[-1:] or [""]
    return last[0].lower().rstrip(".!?") in _ABBREVIATIONS


class SentenceChunker:
    """Feed streamed text in; get back speakable chunks.

    Call `feed(token)` for each streamed token (returns a list of any completed
    chunks, often empty) and `flush()` once at the end (returns any trailing
    text as a final chunk, or None).
    """

    def __init__(self, min_words: int):
        self.min_words = min_words
        # Soft cap: force a flush once pending text reaches this many words, so
        # the first audio is never gated on a period that may never come.
        self.hard_words = min_words * 2
        self._buffer = ""           # text since the last boundary/flush
        self._sentences = []        # complete sentences awaiting a flush

    @property
    def _pending_words(self) -> int:
        return sum(len(s.split()) for s in self._sentences)

    def feed(self, token: str) -> list:
        """Add a token; return a list of completed chunk strings (may be empty)."""
        self._buffer += token
        chunks = []

        # Peel off complete sentences, skipping abbreviations like "Dr."
        search_from = 0
        while True:
            match = SENTENCE_END_PATTERN.search(self._buffer, search_from)
            if not match:
                break
            end = match.end()
            if _ends_with_abbreviation(self._buffer[:end]):
                search_from = end  # not a real boundary; keep scanning
                continue
            sentence = self._buffer[:end].strip()
            self._buffer = self._buffer[end:]  # keep remainder
            search_from = 0
            if sentence:
                self._sentences.append(sentence)
                if self._pending_words >= self.min_words:
                    chunks.append(self._take())

        # Soft cap: a sentence boundary may never come. Once the accumulated text
        # plus the pending buffer is large enough, flush at the earliest clause
        # comma that reaches min_words (or the whole buffer if there's no comma).
        if self._pending_words + len(self._buffer.split()) >= self.hard_words:
            base = self._pending_words
            cut = None
            for cm in CLAUSE_END_PATTERN.finditer(self._buffer):
                if base + len(self._buffer[:cm.end()].split()) >= self.min_words:
                    cut = cm.end()
                    break
            if cut is None:
                cut = len(self._buffer)  # no comma helps; flush all pending text
            head, self._buffer = self._buffer[:cut].strip(), self._buffer[cut:]
            if head:
                self._sentences.append(head)
            piece = self._take()
            if piece:
                chunks.append(piece)

        return chunks

    def flush(self):
        """Return any remaining text as a final chunk (ignores min_words), or None."""
        if self._buffer.strip():
            self._sentences.append(self._buffer.strip())
            self._buffer = ""
        return self._take() or None

    def _take(self) -> str:
        """Join and clear the accumulated sentences; returns the chunk text."""
        text = " ".join(self._sentences).strip()
        self._sentences = []
        return text
