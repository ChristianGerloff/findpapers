import datetime
from urllib.parse import quote_plus
import pytest
from tqdm import tqdm

from findpapers.models.publication import Publication
from findpapers.models.search import Search
from findpapers.searchers.acm_searcher import (
    _get_paper,
    _get_paper_metadata,
    _get_paper_page,
    _get_result,
    _get_search_url,
    run,
)


@pytest.fixture
def test_pbar():
    """Fixture for creating a progress bar object."""
    return tqdm(desc='Progress', total=20)


def test_get_search_url(search: Search):
    """Test the get_search_url function."""
    url = _get_search_url(search)
    query = search.query.replace(' AND NOT ', ' NOT ')
    expected_url = 'https://dl.acm.org/action/doSearch?'
    assert url.startswith(expected_url)
    assert quote_plus(query) in url


def test_get_paper_page():
    """Test the get_paper_page function by mock."""
    paper_page = _get_paper_page()
    assert paper_page is not None


def test_get_paper_metadata():
    """Test the get_paper_metadata function by mock."""
    metadata = _get_paper_metadata()
    assert metadata is not None

    
def test_get_result():
    """Test the get_result function by mock."""
    metadata = _get_result()
    assert metadata is not None


def test_get_paper():
    """Test the get_paper function."""
    paper_page = _get_paper_page()
    paper = _get_paper(paper_page, 'fake-paper-doi', 'fake-url')
    assert paper is not None
    assert paper.title is not None
    assert paper.doi is not None
    assert paper.number_of_pages == 2
    assert len(paper.authors) == 3
    assert paper.publication_date.year == 2020
    assert paper.publication is not None
    assert paper.publication.title == 'Proceedings of the 7th ACM IKDD CoDS and 25th COMAD'
    assert paper.publication.publisher == 'Association for Computing Machinery'
    assert paper.publication.isbn == '9781450377386'


@pytest.mark.skip(reason="It needs some revision after some tool's refactoring")
def test_run(search: Search):
    """Test the run function."""
    search.limit = 14
    search.limit_per_database = None
    run(search)
    assert len(search.papers) == 14


@pytest.mark.parametrize("pbar", [None, pytest.lazy_fixture("test_pbar")])
def test_run_with_or_without_pbar(search: Search, pbar):
    """Test the run function with or without a progress bar."""
    search.limit = 10
    search.limit_per_database = None
    run(search, pbar=pbar)
    assert len(search.papers) == 10
