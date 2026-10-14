from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import psycopg


@dataclass(frozen=True)
class FilterSpec:
    """Declarative filter definition read by the backend to build the filter UI."""

    name: str
    type: str  # "month_range" | "select" | "number_range"
    label: str


class SourceAdapter(ABC):
    """Contract for one kind of Portal da Transparência dataset."""

    name: str
    filters: tuple[FilterSpec, ...]
    display_columns: tuple[str, ...]
    strata_columns: tuple[str, ...]
    feature_columns: tuple[str, ...]

    @abstractmethod
    def parse(self, path: Path) -> pd.DataFrame:
        """Read a raw file and return it normalized for loading into the database."""

    def exclude(self, df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
        """Drop records outside the project scope. Returns the kept rows and the count removed per reason."""
        return df, {}

    @abstractmethod
    def load_population(self, conn: psycopg.Connection) -> pd.DataFrame:
        """Return every analysable record as `id` plus the `strata_columns`, for sampling."""

    @abstractmethod
    def load_features(self, conn: psycopg.Connection, ids: list[int]) -> pd.DataFrame:
        """Return the numeric feature matrix (`feature_columns`) for the given record ids, indexed by id."""
