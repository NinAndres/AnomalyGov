import pandas as pd
import pytest

from anomalygov_ml.sampling import allocate, stratified_sample


def population():
    # Stratum "a": 900 rows, "b": 90 rows, "c": 10 rows.
    sizes = {"a": 900, "b": 90, "c": 10}
    rows = [(stratum, i) for stratum, n in sizes.items() for i in range(n)]
    return pd.DataFrame({"id": range(len(rows)), "stratum": [s for s, _ in rows]})


def test_allocate_is_proportional_with_floor_capped_by_stratum_size():
    sizes = pd.Series({"a": 900, "b": 90, "c": 10})
    assert allocate(sizes, total=100, floor=20).to_dict() == {"a": 90, "b": 20, "c": 10}


def test_allocate_without_floor_is_proportional():
    sizes = pd.Series({"a": 900, "b": 90, "c": 10})
    assert allocate(sizes, total=100, floor=0).to_dict() == {"a": 90, "b": 9, "c": 1}


def test_sample_sizes_and_weights():
    sample = stratified_sample(population(), ["stratum"], total=100, floor=20, seed=42)
    assert sample.groupby("stratum").size().to_dict() == {"a": 90, "b": 20, "c": 10}
    weights = sample.groupby("stratum")["weight"].first()
    assert weights.to_dict() == pytest.approx({"a": 10.0, "b": 4.5, "c": 1.0})
    # Weights add up to the population size.
    assert sample["weight"].sum() == pytest.approx(1000)
    assert sample["id"].is_unique and sample["id"].is_monotonic_increasing


def test_sample_is_reproducible_and_independent_of_row_order():
    pop = population()
    first = stratified_sample(pop, ["stratum"], total=100, floor=20, seed=7)
    shuffled = stratified_sample(pop.sample(frac=1, random_state=1), ["stratum"], total=100, floor=20, seed=7)
    pd.testing.assert_frame_equal(first, shuffled)


def test_different_seeds_draw_different_samples():
    pop = population()
    a = stratified_sample(pop, ["stratum"], total=100, floor=20, seed=1)
    b = stratified_sample(pop, ["stratum"], total=100, floor=20, seed=2)
    assert set(a["id"]) != set(b["id"])
