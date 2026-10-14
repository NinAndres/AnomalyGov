from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


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

    @abstractmethod
    def parse(self, path: Path) -> pd.DataFrame:
        """Read a raw file and return it normalized for loading into the database."""
