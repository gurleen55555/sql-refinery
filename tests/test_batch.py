
import pytest

from app.batch import (
    DEFAULT_BATCH_LIMIT,
    enforce_batch_limit,
    split_sql_queries,
    validate_batch_limit,
)


def test_default_batch_limit_is_10():
    assert DEFAULT_BATCH_LIMIT == 10


def test_batch_within_limit_is_accepted():
    queries = ["SELECT 1", "SELECT 2"]

    assert enforce_batch_limit(queries, 2) == queries


def test_batch_over_limit_is_rejected():
    with pytest.raises(ValueError, match="batch limit"):
        enforce_batch_limit(
            ["SELECT 1", "SELECT 2", "SELECT 3"],
            2,
        )


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_invalid_batch_limits_are_rejected(limit):
    with pytest.raises(ValueError):
        validate_batch_limit(limit)
