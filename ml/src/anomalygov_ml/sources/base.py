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
    label: str
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

    @abstractmethod
    def filter_options(self, conn: psycopg.Connection) -> dict[str, dict]:
        """Extra attributes per filter name, computed from the records in `conn`.

        Select filters get `options` ([{value, label}]); range filters get `min` and `max`.
        """

    def describe(self, conn: psycopg.Connection) -> dict:
        """Definition stored in the `sources` table and read by the backend and the frontend."""
        extra = self.filter_options(conn)
        filters = [{"name": f.name, "type": f.type, "label": f.label, **extra.get(f.name, {})} for f in self.filters]
        return {"name": self.name, "label": self.label, "filters": filters,
                "display_columns": list(self.display_columns)}
