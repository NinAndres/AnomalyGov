"""Stratified sampling shared by every data source (decision 0005)."""

import numpy as np
import pandas as pd


def allocate(sizes: pd.Series, total: int, floor: int) -> pd.Series:
    """Proportional allocation of `total` across strata, with at least `floor` per stratum (or all of it if smaller)."""
    proportional = (sizes / sizes.sum() * total).round().astype(int)
    return proportional.clip(lower=np.minimum(floor, sizes)).clip(upper=sizes)


def stratified_sample(
    population: pd.DataFrame, strata: list[str], total: int, floor: int, seed: int
) -> pd.DataFrame:
    """Draw a stratified sample of `population` rows (which must have an `id` column).

    Returns the sampled rows sorted by id, with a `weight` column (stratum size / rows drawn).
    The result depends only on the population content and the seed, not on the row order.
    """
    population = population.sort_values("id", ignore_index=True)
    groups = population.groupby(strata, sort=True)
    sizes = groups.size()
    allocation = allocate(sizes, total, floor)
    rng = np.random.default_rng(seed)

    parts = []
    for key, rows in groups:
        key = key[0] if len(strata) == 1 else key  # groupby yields 1-tuples for a single column
        k = allocation[key]
        if k == 0:
            continue
        chosen = rows.iloc[np.sort(rng.choice(len(rows), size=k, replace=False))]
        parts.append(chosen.assign(weight=sizes[key] / k))
    return pd.concat(parts).sort_values("id", ignore_index=True)
