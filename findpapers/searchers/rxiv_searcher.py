import logging
import datetime
from typing import List
from lxml import html
import findpapers.utils.query_util as query_util
import findpapers.utils.common_util as common_util
from findpapers.models.search import Search
from findpapers.models.paper import Paper
from findpapers.models.publication import Publication
from findpapers.utils.requests_util import DefaultSession


BASE_URL = 'https://www.medrxiv.org'
API_BASE_URL = 'https://api.biorxiv.org'


def _get_search_urls(search: Search, database: str) -> List[str]:
    """
    This method return the URL to be used to
    retrieve data from medRxiv/bioRxiv database.
    See https://www.medrxiv.org/content/search-tips for query tips

    Parameters
    ----------
    search : Search
        A search instance
    database : str
        The database name (medRxiv or bioRxiv)

    Returns
    -------
    List[str]
        a URL list to be used to retrieve data from medRxiv/bioRxiv database
    """

    # The databases don't support wildcards properly nowadays
    if '?' in search.query or '*' in search.query:
        raise ValueError('Queries with wildcards are not '
                         'supported by medRxiv/bioRxiv database')

    # NOT connectors aren't supported
    if ' AND NOT ' in search.query:
        raise ValueError('NOT connectors aren\'t supported')

    # Parentheses are used for URL splitting purposes and only
    # 1-level grouping is supported with an OR connector between the groups
    current_level = 0
    for character in search.query:
        if character == '(':
            current_level += 1
        elif character == ')':
            current_level -= 1
        if current_level > 1:
            raise ValueError('Max 1-level parentheses grouping exceeded')

    if ') AND (' in search.query:
        raise ValueError('Only the OR connector can '
                         'be used between the groups')

    query = query_util.apply_on_each_term(
        search.query, lambda x: x.replace(' ', '+'))
    queries = query.split(') OR (')
    queries = [x[1:] if x[0] == '(' else x for x in queries]
    queries = [x[:-1] if x[-1] == ')' else x for x in queries]

    urls = []

    date_pattern = '%Y-%m-%d'
    since = (search.since.strftime(date_pattern) if
             search.since is not None else
             '1970-01-01')
    until = (search.until.strftime(date_pattern) if
             search.until is not None else
             datetime.datetime.now().strftime(date_pattern))
    date_parameter = f'limit_from%3A{since}%20limit_to%3A{until}'

    url_suffix = (f'jcode%3A{database.lower()}%20{date_parameter}%20'
                  "numresults%3A75%20"
                  "sort%3Apublication-date%20"
                  "direction%3Adescending%20"
                  "format_result%3Acondensed")

    for query in queries:
        ors_count = len(query.split(' OR ')) - 1
        ands_count = len(query.split(' AND ')) - 1

        # All the inner connectors of the groups needs to be the same
        if ors_count > 0 and ands_count > 0:
            raise ValueError('Mixed inner connectors found. '
                             'Each query group must use only one connector '
                             f' type, only ANDs or only ORs: {query}')

        query_match_flag = 'match-any'
        if ands_count > 0:
            query_match_flag = 'match-all'

        encoded_query = (query.replace('+', '%252B').
                         replace(' OR ', '%2B').
                         replace(' AND ', '%2B').
                         replace('[', '%2522').
                         replace(']', '%2522'))

        url = (f'{BASE_URL}/search/'
               f'abstract_title%3A{encoded_query}'
               f'%20abstract_title_flags%3A{query_match_flag}'
               f'%20{url_suffix}')
        urls.append(url)

    return urls


def _get_result(url: str) -> html.HtmlElement:  # pragma: no cover
    """
    This method return results from medRxiv/bioRxiv
    database using the provided search parameters

    Parameters
    ----------
    url : str
        A URL to search for results

    Returns
    -------
    html.HtmlElement
        a page from medRxiv/bioRxiv database
    """

    response = common_util.try_success(lambda: DefaultSession().get(url), 2)
    return html.fromstring(response.content)


def _get_result_page_data(result_page: html.HtmlElement) -> dict:
    """
    Extract results data from the given result page

    Parameters
    ----------
    result_page : html.HtmlElement
        A result page extracted from medRxiv/bioRxiv database

    Returns
    -------
    dict
        a dict containing papers DOis, total_papers and next_page_url info
    """

    total_papers = result_page.xpath('//*[@id="page-title"]/text()')[0].strip()
    if 'no results' in total_papers.lower():
        total_papers = 0
    else:
        total_papers = int(total_papers.split()[0].replace(',', ''))

    dois = []
    next_page_url = None

    if total_papers > 0:

        dois = result_page.xpath('//*[@class="highwire-cite-metadata-doi '
                                 'highwire-cite-metadata"]/text()')
        dois = [x.strip().replace('https://doi.org/', '') for x in dois]

        next_page_elements = result_page.xpath('//*[@class="link-icon'
                                               ' link-icon-after"]')
        if len(next_page_elements) > 0:
            next_page_url = next_page_elements[0].attrib['href']
            next_page_url = BASE_URL + next_page_url

    data = {
        'dois': dois,
        'total_papers': total_papers,
        'next_page_url': next_page_url
    }

    return data


def _get_paper_metadata(doi: str, database: str) -> dict:  # pragma: no cover
    """
    Get a paper metadata from a provided DOI

    Parameters
    ----------
    doi : str
        The paper DOI
    database : str
        The database name (medRxiv or bioRxiv)

    Returns
    -------
    dict
        The medRxiv/bioRxiv paper metadata,
        or None if there's no metadata available
    """

    url = f'{API_BASE_URL}/details/{database.lower()}/{doi}'

    response = common_util.try_success(
        lambda: DefaultSession().get(url).json(), 2)
    if (response is not None and
        response.get('collection', None) is not None and
            len(response.get('collection')) > 0):
        return response.get('collection')[0]


def _get_data(url: str) -> List[dict]:
    """
    Get the data list from medRxiv/bioRxiv given the search url

    Parameters
    ----------
    url : str
        A search URL

    Returns
    -------
    List[dict]
        Data list
    """

    result_page = _get_result(url)
    page_data = _get_result_page_data(result_page)
    data = [page_data]

    if page_data.get('next_page_url') is not None:
        data = data + _get_data(page_data.get('next_page_url'))

    return data


def _get_publication(paper_entry: dict, database: str) -> Publication:
    """
    Using a paper entry provided, this method builds a publication instance

    Parameters
    ----------
    paper_entry : dict
        A paper entry retrieved from rXiv API

    database : str
       The name of database is set as the preprint title.

    Returns
    -------
    Publication, or None
        A publication instance
    """

    publication_title = database  # unpublished preprints

    subject_areas = set()
    if 'category' in paper_entry:
        if isinstance(paper_entry.get('category'), list):
            for category in paper_entry.get('category'):
                subject_areas.add(category)
        else:
            subject_areas.add(paper_entry.get('category'))
    publication = Publication(publication_title,
                              category='Preprint',
                              subject_areas=subject_areas)
    return publication


def _get_paper(paper_metadata: dict, database: str) -> Paper:
    """
    Get Paper object from metadata

    Parameters
    ----------
    paper_metadata : dict
        Paper metadata

    database : str
        Name of database

    Returns
    -------
    Paper
        Paper object
    """

    paper_title = paper_metadata.get('title')
    paper_abstract = paper_metadata.get('abstract')
     # exclude cross-refs without abstracts
    if paper_abstract is not None:
        remove_abstract = ['<h3>Abstract</h3>',
                           '<p>', '</p>']
        for i in remove_abstract:
            paper_abstract = paper_abstract.replace(i, '')
    paper_authors = [x.strip() for x in
                     paper_metadata.get('authors').split(';')]
    publication = None
    paper_publication_date = (datetime.datetime.
                              strptime(paper_metadata.get('date'),
                                       '%Y-%m-%d').
                              date())
    paper_url = f'https://doi.org/{paper_metadata.get("doi")}'
    paper_doi = paper_metadata.get("doi")
    paper_citations = None
    paper_keywords = None
    paper_comments = None
    paper_number_of_pages = None
    paper_pages = None

    if paper_metadata.get('published').lower() != 'na':
        # replace doi if published
        paper_doi = paper_metadata.get('published').replace('\\', '')

    publication = _get_publication(paper_metadata, database)  # create pub obj

    return Paper(paper_title, paper_abstract, paper_authors, publication,
                 paper_publication_date, {paper_url}, paper_doi,
                 paper_citations, paper_keywords,
                 paper_comments, paper_number_of_pages, paper_pages)


def run(search: Search, database: str, pbar=None):
    """
    This method fetch papers from medRxiv/bioRxiv database using
    the provided search parameters.
    After fetch the data from medRxiv/bioRxiv,
    the collected papers are added to the provided search instance

    Parameters
    ----------
    search : Search
        A search instance
    database : str
        The database name (medRxiv or bioRxiv)
    pbar: stqdm.stqdm.stqdm
        stqdm instance for progress bar.  Defaults to None.
    """

    urls = _get_search_urls(search, database)

    for i, url in enumerate(urls):

        if search.reached_its_limit(database):
            break

        logging.info(f'{database}: Requesting for papers...')

        data = _get_data(url)  # parse response

        total_papers = 0
        if len(data) > 0:
            total_papers = data[0].get('total_papers')

        logging.info(f'{database}: {total_papers} '
                     'papers to fetch from '
                     f'{i+1}/{len(urls)} sub queries')

        papers_count = 0
        dois = sum([d.get('dois') for d in [x for x in data]], [])

        for doi in dois:
            #  stop after user specified limit
            if (papers_count >= total_papers or
                    search.reached_its_limit(database)):
                break
            try:
                papers_count += 1
                paper_metadata = _get_paper_metadata(doi, database)

                paper_title = paper_metadata.get('title')

                logging.info(f'({papers_count}/{total_papers}) '
                             f'Fetching {database} paper: {paper_title}')

                paper = _get_paper(paper_metadata, database)
                paper.add_database(database)
                search.add_paper(paper)

            except Exception as e:  # pragma: no cover
                logging.debug(e, exc_info=True)
            
            try:
                if pbar is not None:
                    pbar.update(1)
            except Exception as e:  # pragma: no cover
                logging.debug(e, exc_info=True)
