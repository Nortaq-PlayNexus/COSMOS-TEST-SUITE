"""
Literature ingestion for COSMOS TEST SUITE.

Section 5 of the specification requires a local research database populated
from primary sources, and Section 6 requires an ingestion engine that can
find papers and collect their metadata.

This module implements that against the arXiv API, which is the one primary
literature source reachable without credentials.

Design rules, in order of importance:

1. **Never invent a citation.** Every record returned by this module came from
   a live API response and carries the arXiv ID and DOI exactly as published.
   Nothing is synthesised, completed, or guessed.

2. **Never auto-extract numbers into results tables.** Abstracts contain
   numbers, but scraping "67.4 +/- 0.5" out of prose is a transcription risk
   with no error detection. Abstracts are stored verbatim so a human or a
   later, verified extraction can read them. This keeps §2's separation of
   *observation* from *inference* intact.

3. **Fail honestly.** If the network is unavailable the caller gets an
   explicit failure, never an empty result presented as "no such paper exists".

Rate limiting follows the arXiv API terms: one request at a time, with a
delay between requests.
"""

from __future__ import annotations

import datetime
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"

API_URL = "http://export.arxiv.org/api/query"

# arXiv's API terms of use ask for no more than one request every three
# seconds, and no parallel requests.
MIN_REQUEST_INTERVAL_S = 3.0

USER_AGENT = "COSMOS-Test-Suite/0.1 (research software; contact via repository)"


class IngestionError(Exception):
    """Raised when literature cannot be retrieved. Never swallowed silently."""


@dataclass
class PaperRecord:
    """
    Metadata for one paper, taken verbatim from the arXiv API response.

    Every field is either supplied by the API or absent. Nothing is filled in
    from memory or inferred.
    """

    arxiv_id: str
    title: str
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    published: Optional[str] = None      # ISO date, from the API
    updated: Optional[str] = None        # ISO date, from the API
    doi: Optional[str] = None            # may be absent for preprints
    journal_ref: Optional[str] = None
    categories: List[str] = field(default_factory=list)
    pdf_url: Optional[str] = None
    abs_url: Optional[str] = None
    # Provenance: where this record came from and when it was retrieved.
    source: str = "arXiv API"
    retrieved_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    query: Optional[str] = None          # the query that found this paper

    @property
    def short_id(self) -> str:
        """arXiv ID without any version suffix."""
        return self.arxiv_id.split("v")[0] if "v" in self.arxiv_id else self.arxiv_id

    def citation_string(self) -> str:
        """
        A citation built only from fields the API actually supplied.

        If the API gave no DOI, none is invented; the arXiv ID is used
        instead, which the API always provides.
        """
        if not self.authors:
            who = "Unknown author"
        elif len(self.authors) == 1:
            who = self.authors[0]
        else:
            who = f"{self.authors[0]} et al."
        year = (self.published or "")[:4] or "n.d."
        ident = f"doi:{self.doi}" if self.doi else f"arXiv:{self.short_id}"
        return f"{who} ({year}). {self.title}. {ident}"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["short_id"] = self.short_id
        d["citation_string"] = self.citation_string()
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PaperRecord":
        d = dict(d)
        d.pop("short_id", None)
        d.pop("citation_string", None)
        return cls(**d)


def _text(entry: ET.Element, tag: str) -> str:
    """Fetch an element's text with whitespace collapsed."""
    node = entry.find(tag)
    if node is None or node.text is None:
        return ""
    return " ".join(node.text.split())


def _parse_entry(entry: ET.Element, query: Optional[str]) -> PaperRecord:
    raw_id = _text(entry, f"{ATOM}id")
    arxiv_id = raw_id.rsplit("/", 1)[-1] if raw_id else ""
    abs_url = raw_id or None

    doi = entry.findtext(f"{ARXIV_NS}doi")
    journal_ref = entry.findtext(f"{ARXIV_NS}journal_ref")

    authors = [
        " ".join((a.findtext(f"{ATOM}name") or "").split())
        for a in entry.findall(f"{ATOM}author")
    ]
    categories = [
        c.attrib.get("term", "") for c in entry.findall(f"{ATOM}category")
    ]
    pdf_url = None
    for link in entry.findall(f"{ATOM}link"):
        if link.attrib.get("title") == "pdf":
            pdf_url = link.attrib.get("href")

    published = _text(entry, f"{ATOM}published") or None
    updated = _text(entry, f"{ATOM}updated") or None
    if published:
        published = published[:10]

    return PaperRecord(
        arxiv_id=arxiv_id,
        title=_text(entry, f"{ATOM}title"),
        authors=authors,
        abstract=_text(entry, f"{ATOM}summary"),
        published=published,
        updated=updated,
        doi=doi,
        journal_ref=journal_ref,
        categories=categories,
        pdf_url=pdf_url,
        abs_url=abs_url,
        query=query,
    )


class ArxivClient:
    """
    Rate-limited client for the arXiv API.

    Every call is throttled to one request per MIN_REQUEST_INTERVAL_S, with
    retries on transient failures. Failures raise IngestionError so a caller
    can never mistake "the network is down" for "no such paper".
    """

    def __init__(
        self,
        cache_dir: Optional[Path | str] = None,
        offline: bool = False,
        min_interval: float = MIN_REQUEST_INTERVAL_S,
        timeout: int = 30,
        retries: int = 3,
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else Path("papers/cache")
        self.offline = offline
        self.min_interval = min_interval
        self.timeout = timeout
        self.retries = retries
        self._last_request: float = 0.0
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # -- throttling -------------------------------------------------------

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request = time.monotonic()

    # -- cache ------------------------------------------------------------

    def _cache_path(self, query: str, max_results: int) -> Path:
        safe = urllib.parse.quote(query, safe="")[:120]
        return self.cache_dir / f"q_{safe}_{max_results}.json"

    def _read_cache(self, path: Path, max_age_s: float = 86400.0) -> Optional[List[PaperRecord]]:
        if not path.exists():
            return None
        if time.time() - path.stat().st_mtime > max_age_s:
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return [PaperRecord.from_dict(d) for d in payload.get("papers", [])]

    def _write_cache(self, path: Path, papers: List[PaperRecord]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"papers": [p.to_dict() for p in papers]}, indent=2),
            encoding="utf-8",
        )

    # -- retrieval --------------------------------------------------------

    def search(
        self,
        query: str,
        max_results: int = 10,
        sort_by: str = "relevance",
    ) -> List[PaperRecord]:
        """
        Search arXiv and return records.

        Parameters
        ----------
        query : arXiv search syntax, e.g. 'all:"cosmic topology"'
        max_results : cap on returned records
        sort_by : relevance | submittedDate | lastUpdatedDate

        Raises
        ------
        IngestionError
            If offline with no cache, or if every retry fails. Callers must
            handle this; it never means "zero results found".
        """
        cache_file = self._cache_path(query, max_results)

        if self.offline:
            cached = self._read_cache(cache_file, max_age_s=float("inf"))
            if cached is None:
                raise IngestionError(
                    f"offline mode and no cached response for query {query!r}; "
                    "cannot verify whether papers exist. This is NOT evidence "
                    "that the literature is empty."
                )
            return cached

        cached = self._read_cache(cache_file)
        if cached is not None:
            return cached

        params = {
            "search_query": query,
            "max_results": str(max_results),
            "sortBy": sort_by,
        }
        url = f"{API_URL}?{urllib.parse.urlencode(params)}"

        last_error: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            self._throttle()
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": USER_AGENT}
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read()
                root = ET.fromstring(body)
                papers = [
                    _parse_entry(e, query)
                    for e in root.findall(f"{ATOM}entry")
                ]
                papers = [p for p in papers if p.arxiv_id]
                self._write_cache(cache_file, papers)
                return papers
            except (urllib.error.URLError, ET.ParseError, OSError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(2.0 * attempt)

        raise IngestionError(
            f"arXiv query {query!r} failed after {self.retries} attempts: "
            f"{last_error}. This is a retrieval failure, not an empty result."
        )

    def get_by_id(self, arxiv_id: str) -> Optional[PaperRecord]:
        """Fetch one paper by arXiv ID. Returns None only if arXiv says 404."""
        papers = self.search(f"id_list:{arxiv_id}", max_results=1)
        return papers[0] if papers else None

    def availability(self) -> Dict[str, Any]:
        """
        Report whether the API is reachable, without pretending.

        Returns a dict with 'reachable', 'detail', and 'checked_at'. Used by the
        CLI so an operator can tell the difference between "offline" and
        "no results".
        """
        if self.offline:
            return {
                "reachable": False,
                "detail": "client is in offline mode",
                "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        try:
            self._throttle()
            req = urllib.request.Request(
                f"{API_URL}?{urllib.parse.urlencode({'search_query': 'all:cosmology', 'max_results': '1'})}",
                headers={"User-Agent": USER_AGENT},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp.read(512)
            return {
                "reachable": True,
                "detail": f"arXiv API responded {resp.status}",
                "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        except Exception as exc:
            return {
                "reachable": False,
                "detail": f"{type(exc).__name__}: {exc}",
                "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }


class LiteratureStore:
    """
    A local, queryable corpus of PaperRecords.

    Backed by a JSON file so the corpus is inspectable, diffable, and
    reviewable in a pull request. Records carry their retrieval timestamp and
    originating query, so provenance survives into the database.
    """

    def __init__(self, path: Optional[Path | str] = None) -> None:
        self.path = Path(path) if path else Path("papers/metadata/corpus.json")
        self.records: Dict[str, PaperRecord] = {}

    def load(self) -> "LiteratureStore":
        if self.path.exists():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                for d in payload.get("papers", []):
                    rec = PaperRecord.from_dict(d)
                    self.records[rec.short_id] = rec
            except (json.JSONDecodeError, OSError, TypeError) as exc:
                # A corrupt corpus must not silently yield an empty corpus.
                raise IngestionError(
                    f"corpus file {self.path} is unreadable ({exc}); refusing "
                    "to treat it as an empty literature search"
                ) from exc
        return self

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "n_papers": len(self.records),
            "source": "arXiv API (see each record's retrieved_at and query)",
            "papers": [r.to_dict() for r in self.records.values()],
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def add(self, record: PaperRecord) -> PaperRecord:
        existing = self.records.get(record.short_id)
        # Keep whichever copy has a DOI: an older response may predate the
        # journal reference being added.
        if existing is None or (not existing.doi and record.doi):
            self.records[record.short_id] = record
        return self.records[record.short_id]

    def add_all(self, records: List[PaperRecord]) -> int:
        before = len(self.records)
        for r in records:
            self.add(r)
        return len(self.records) - before

    def search(self, terms: str, limit: int = 10) -> List[PaperRecord]:
        """
        Substring search across title, abstract, authors, and categories.

        All terms must appear somewhere in the record (AND semantics), which
        keeps 'dark energy DESI' from returning papers that mention only one.
        """
        wanted = [t.lower() for t in terms.split() if t.strip()]
        if not wanted:
            return []

        hits = []
        for rec in self.records.values():
            haystack = " ".join(
                [rec.title, rec.abstract, " ".join(rec.authors), " ".join(rec.categories)]
            ).lower()
            if all(t in haystack for t in wanted):
                hits.append(rec)

        hits.sort(key=lambda r: (r.published or ""), reverse=True)
        return hits[:limit]

    def __len__(self) -> int:
        return len(self.records)

    def stats(self) -> Dict[str, Any]:
        with_doi = sum(1 for r in self.records.values() if r.doi)
        years: Dict[str, int] = {}
        for r in self.records.values():
            y = (r.published or "")[:4]
            if y:
                years[y] = years.get(y, 0) + 1
        return {
            "n_papers": len(self.records),
            "with_doi": with_doi,
            "with_abstract": sum(1 for r in self.records.values() if r.abstract),
            "by_year": dict(sorted(years.items())),
            "corpus_path": str(self.path),
        }
