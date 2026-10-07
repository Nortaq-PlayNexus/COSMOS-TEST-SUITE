"""
Tests for literature ingestion.

The point of these tests is that ingestion must never fabricate. A record has
to carry a real identifier, a real query that found it, and a real retrieval
time; a retrieval failure must be distinguishable from an empty result.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cosmos.ingestion import (
    ArxivClient,
    IngestionError,
    LiteratureStore,
    PaperRecord,
)

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"

# A minimal but structurally faithful arXiv API response, used so the parser
# is tested without touching the network.
SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/1505.03549v2</id>
    <published>2015-05-12T00:00:00Z</published>
    <updated>2017-01-03T00:00:00Z</updated>
    <title>  The clustering of galaxies and the large-scale structure
      of the universe  </title>
    <summary>  We present a measurement of the matter power spectrum
      from the BOSS DR12 consensus.  </summary>
    <author><name>Shen, Yue</name></author>
    <author><name>Yang, Qian</name></author>
    <author><name>Abbott, Michael</name></author>
    <arxiv:doi xmlns:arxiv="http://arxiv.org/schemas/atom">10.1088/0004-637X/799/2/L147</arxiv:doi>
    <arxiv:journal_ref xmlns:arxiv="http://arxiv.org/schemas/atom">ApJ 799, L147 (2015)</arxiv:journal_ref>
    <category term="astro-ph.CO"/>
    <link href="http://arxiv.org/abs/1505.03549v2" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/1505.03549v2" rel="related" type="application/pdf"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/9999.99999v1</id>
    <published>2000-01-01T00:00:00Z</published>
    <title>A preprint with no DOI and no journal reference</title>
    <summary>An abstract.</summary>
    <author><name>Solo Author</name></author>
    <category term="gr-qc"/>
  </entry>
</feed>
"""


@pytest.fixture
def sample_records():
    """Parse the sample feed into PaperRecords."""
    import xml.etree.ElementTree as ET

    from cosmos.ingestion import _parse_entry

    root = ET.fromstring(SAMPLE_ATOM)
    return [_parse_entry(e, "test query") for e in root.findall(f"{ATOM}entry")]


class TestParsing:
    def test_parses_all_expected_fields(self, sample_records):
        r = sample_records[0]
        assert r.arxiv_id == "1505.03549v2"
        assert r.short_id == "1505.03549"
        assert r.doi == "10.1088/0004-637X/799/2/L147"
        assert r.journal_ref == "ApJ 799, L147 (2015)"
        assert r.published == "2015-05-12"

    def test_title_and_abstract_are_whitespace_collapsed(self, sample_records):
        r = sample_records[0]
        assert "\n" not in r.title
        assert r.title.startswith("The clustering of galaxies")
        assert "\n" not in r.abstract

    def test_all_authors_captured(self, sample_records):
        assert sample_records[0].authors == [
            "Shen, Yue",
            "Yang, Qian",
            "Abbott, Michael",
        ]

    def test_categories_and_urls(self, sample_records):
        r = sample_records[0]
        assert "astro-ph.CO" in r.categories
        assert r.pdf_url is not None
        assert r.abs_url is not None

    def test_record_without_doi_is_not_given_one(self, sample_records):
        """The API omitted a DOI, so the record must have none."""
        assert sample_records[1].doi is None
        assert "doi:" not in sample_records[1].citation_string()


class TestCitationString:
    def test_single_author(self, sample_records):
        rec = sample_records[1]
        rec.authors = ["Solo Author"]
        c = rec.citation_string()
        assert "Solo Author (2000)" in c
        assert "et al." not in c

    def test_two_authors_use_et_al_without_a_count(self, sample_records):
        rec = sample_records[0]
        rec.authors = ["A One", "B Two"]
        c = rec.citation_string()
        assert "A One et al. (2015)" in c
        # A redundant author count reads badly and is not standard.
        assert "authors)" not in c

    def test_doi_used_when_present(self, sample_records):
        assert "doi:10.1088/0004-637X/799/2/L147" in sample_records[0].citation_string()

    def test_arxiv_id_used_when_no_doi(self, sample_records):
        assert "arXiv:9999.99999" in sample_records[1].citation_string()

    def test_no_author_does_not_crash(self, sample_records):
        rec = sample_records[0]
        rec.authors = []
        assert "Unknown author" in rec.citation_string()

    def test_missing_date_is_marked_not_invented(self, sample_records):
        rec = sample_records[0]
        rec.published = None
        assert "n.d." in rec.citation_string()


class TestRoundTrip:
    def test_record_survives_serialisation(self, sample_records):
        original = sample_records[0]
        restored = PaperRecord.from_dict(original.to_dict())
        assert restored.arxiv_id == original.arxiv_id
        assert restored.doi == original.doi
        assert restored.authors == original.authors
        assert restored.abstract == original.abstract

    def test_citation_is_stable_across_round_trip(self, sample_records):
        original = sample_records[0]
        restored = PaperRecord.from_dict(original.to_dict())
        assert restored.citation_string() == original.citation_string()


class TestStore:
    def test_add_and_search(self, sample_records, tmp_path):
        store = LiteratureStore(tmp_path / "corpus.json")
        store.add_all(sample_records)
        hits = store.search("clustering")
        assert len(hits) == 1
        assert "BOSS" in hits[0].abstract

    def test_search_requires_all_terms(self, sample_records, tmp_path):
        """'matter power' should not match a record lacking one of them."""
        store = LiteratureStore(tmp_path / "corpus.json")
        store.add_all(sample_records)
        assert store.search("matter spectrum")          # both present
        assert store.search("matter nonexistentword") == []  # one absent

    def test_deduplicates_by_short_id(self, sample_records, tmp_path):
        store = LiteratureStore(tmp_path / "corpus.json")
        store.add(sample_records[0])
        store.add(sample_records[0])
        assert len(store) == 1

    def test_upgrade_keeps_the_record_with_a_doi(self, sample_records, tmp_path):
        """
        An earlier response may predate the journal reference appearing, so a
        later copy carrying a DOI must replace it.
        """
        store = LiteratureStore(tmp_path / "corpus.json")
        without_doi = sample_records[0]
        without_doi.doi = None
        store.add(without_doi)
        with_doi = sample_records[0]
        with_doi.doi = "10.1088/0004-637X/799/2/L147"
        store.add(with_doi)
        assert store.records[with_doi.short_id].doi == "10.1088/0004-637X/799/2/L147"

    def test_persists_and_reloads(self, sample_records, tmp_path):
        path = tmp_path / "corpus.json"
        store = LiteratureStore(path)
        store.add_all(sample_records)
        store.save()

        reloaded = LiteratureStore(path).load()
        assert len(reloaded) == len(store)

    def test_saved_file_declares_its_own_size(self, sample_records, tmp_path):
        path = tmp_path / "corpus.json"
        store = LiteratureStore(path)
        store.add_all(sample_records)
        store.save()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["n_papers"] == len(store)
        assert "arXiv" in payload["source"]

    def test_corrupt_corpus_raises_rather_than_reading_as_empty(self, tmp_path):
        """
        A truncated or corrupt corpus file must not be silently treated as
        'no literature exists'. That failure mode would make a missing file
        indistinguishable from an empty field.
        """
        path = tmp_path / "corpus.json"
        path.write_text("{ this is not valid json", encoding="utf-8")
        with pytest.raises(IngestionError):
            LiteratureStore(path).load()

    def test_stats_counts_dois(self, sample_records, tmp_path):
        store = LiteratureStore(tmp_path / "corpus.json")
        store.add_all(sample_records)
        stats = store.stats()
        assert stats["n_papers"] == 2
        assert stats["with_doi"] == 1
        assert stats["with_abstract"] == 2


class TestOfflineBehaviour:
    def test_offline_with_no_cache_raises(self, tmp_path):
        """
        Offline with no cached response must raise. Returning an empty list
        would let a caller report 'no such paper exists', which the ingestion
        failure does not support.
        """
        client = ArxivClient(cache_dir=tmp_path, offline=True)
        with pytest.raises(IngestionError) as exc:
            client.search("all:cosmology")
        assert "NOT evidence" in str(exc.value)

    def test_offline_uses_cache_when_present(self, sample_records, tmp_path):
        client = ArxivClient(cache_dir=tmp_path, offline=True)
        # The cache key includes max_results, so the read must use the same one.
        client._write_cache(client._cache_path("q", 5), sample_records)

        cached = client.search("q", max_results=5)
        assert len(cached) == 2
        assert cached[0].doi == sample_records[0].doi

    def test_cache_key_distinguishes_result_limits(self, tmp_path):
        client = ArxivClient(cache_dir=tmp_path)
        assert client._cache_path("q", 5) != client._cache_path("q", 10)

    def test_availability_reports_offline(self, tmp_path):
        client = ArxivClient(cache_dir=tmp_path, offline=True)
        status = client.availability()
        assert status["reachable"] is False
        assert "offline" in status["detail"]

    def test_availability_has_a_timestamp(self, tmp_path):
        status = ArxivClient(cache_dir=tmp_path, offline=True).availability()
        assert "checked_at" in status


class TestShippedCorpus:
    """
    If a corpus is committed to the repository, it must be genuine: every
    record needs an arXiv ID, provenance, and a citation that resolves.
    """

    @pytest.fixture(scope="class")
    def corpus(self):
        path = Path(__file__).resolve().parent.parent / "papers" / "metadata" / "corpus.json"
        if not path.exists():
            pytest.skip("no corpus committed")
        return LiteratureStore(path).load()

    def test_corpus_is_not_empty(self, corpus):
        assert len(corpus) > 0

    def test_every_record_has_an_arxiv_id(self, corpus):
        missing = [sid for sid, r in corpus.records.items() if not r.arxiv_id]
        assert missing == []

    def test_every_record_has_provenance(self, corpus):
        missing = [
            sid for sid, r in corpus.records.items()
            if not r.query or not r.retrieved_at
        ]
        assert missing == []

    def test_every_record_has_a_title(self, corpus):
        assert all(r.title for r in corpus.records.values())

    def test_citations_are_unique(self, corpus):
        """Duplicate citations would suggest duplicated ingestion."""
        citations = [r.citation_string() for r in corpus.records.values()]
        assert len(set(citations)) == len(citations)

    def test_dois_look_like_dois(self, corpus):
        for r in corpus.records.values():
            if r.doi:
                assert r.doi.startswith("10."), f"malformed DOI: {r.doi}"

    def test_publication_years_are_plausible(self, corpus):
        for r in corpus.records.values():
            if r.published:
                year = int(r.published[:4])
                assert 1991 <= year <= 2030, f"implausible year {year} in {r.arxiv_id}"
