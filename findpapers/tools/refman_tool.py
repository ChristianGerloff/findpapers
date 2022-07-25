""""
Class to parse search results to a RIS compatible format.
"""
import logging
import datetime
import rispy
import pandas as pd

from dataclasses import dataclass, asdict
from typing import List
from findpapers.models.search import Search


def _spit_page_information(pages: str = None):
    """Split page information into start and end page.

    Args:
        pages (str, optional): page string. Defaults to None.

    Returns:
        str: start_page, end_page
    """

    if pages is None:
        return '', ''
    if '-' in pages:
        return pages.split('-')
    elif ',' in pages:
        return pages.split(',')
    elif ' ' in pages:
        return pages.split(' ')
    else:
        return pages, ''


@dataclass
class RisPaper:
    id: int
    abstract: str
    authors: List[str]
    custom1: int
    custom2: List[str]
    date: datetime
    name_of_database: List[str]
    doi: str
    start_page: str
    end_page: str
    alternate_title3: str
    journal_name: str
    keywords: List[str]
    label: bool
    notes: str
    publisher: str
    year: int
    reviewed_item: bool
    issn: str
    title: str
    type_of_reference: str
    url: List[str]
    publication_year: int
    access_date: datetime


class RisExport:
    "Riss compatible export class"
    def __init__(self,
                 search_results: Search):
        self.search = search_results

    @property
    def ris(self) -> list:
        """List of papers.

        Returns:
            list: pandas compatible search results
        """
        return self.__ris

    @property
    def search(self) -> Search:
        """Results of literature search.

        Returns:
            Search: search results
        """
        return self.__search

    @search.setter
    def search(self, search_results):
        if len(search_results.papers) > 0:
            self.__search = search_results
            self._convert_to_ris()

    def _convert_to_ris(self):
        """converts findpapers results to RIS format."""
        papers = self.search.papers

        entry_type = {"Journal": "JOUR",
                      "Book": "BOOK",
                      "Conference Proceedings": "CONF",
                      "Preprint": "UNPB"}

        try:
            ris = [RisPaper(id=i,
                            abstract=p.abstract,
                            authors=p.authors,
                            custom1=p.citations,
                            custom2=list(p.publication.subject_areas),
                            date=p.publication_date,
                            name_of_database=list(p.databases),
                            doi=p.doi,
                            start_page=_spit_page_information(p.pages)[0],
                            end_page=_spit_page_information(p.pages)[1],
                            alternate_title3=p.publication.title,
                            journal_name=p.publication.title,
                            keywords=list(p.keywords),
                            label=p.selected,
                            notes=p.comments,
                            publisher=p.publication.publisher,
                            year=p.publication_date.year,
                            reviewed_item=(True if p.selected is not None
                                           else False),
                            issn=p.publication.issn,
                            title=p.title,
                            type_of_reference=entry_type.get(
                                p.publication.category, "JOUR"),
                            url=list(p.urls),
                            publication_year=p.publication_date.year,
                            access_date=self.search.processed_at.date())
                   for i, p in enumerate(papers, 1)]  # start key from 1
        except Exception:
            logging.warning('Results can not be converted to RIS',
                            exc_info=True)
        else:
            self.__ris = ris

    def generate_ris(self, filename: str = None):
        """Converts and saves search results as ris

        Args:
            filename (str, optional): filename of csv. Defaults to None.

        Returns:
            ris: a RIS compatible and encoded txtio obj. Defaults to None.
            papers: pandas dataframe of ris objects. Defaults to None.
        """

        if hasattr(self, 'ris'):
            papers = pd.DataFrame(self.ris)

            # convert to ris
            raw_entries = [asdict(p) for p in self.ris]  # convert to dict
            entries = [{k: v for k, v in p.items() if v is not None}
                       for p in raw_entries]
            ris = rispy.dumps(entries,
                              skip_unknown_tags=True,
                              enforce_list_tags=False)  # convert to ris

            with open(filename, 'w') as file:
                file.writelines(ris)
        else:
            papers = None
            ris = None
            logging.info('Empty results')
        return ris, papers
