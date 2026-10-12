from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import pytest

from easy_tdx import (
    DataProvenance,
    HostHealthRegistry,
    Market,
    TdxClient,
    TdxSemanticError,
    get_provenance,
)
from easy_tdx.derive.formula import evaluate
from easy_tdx.storage import ParquetSink, StorageError


def _bars(offset: float) -> pd.DataFrame:
    return pd.DataFrame({"close": [offset + i for i in range(8)], "vol": [1.0] * 8})


def test_formula_context_isolated_between_threads() -> None:
    def run(offset: float) -> float:
        result = evaluate("X: OBV();", _bars(offset))
        return float(result.iloc[-1, 0])

    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(run, [1.0, 10.0, 100.0, 1000.0]))
    assert values == [7.0, 7.0, 7.0, 7.0]


def test_provenance_round_trip() -> None:
    frame = pd.DataFrame({"value": [1]})
    provenance = DataProvenance(source="fixture", is_approximate=True)
    frame.attrs["provenance"] = provenance.to_dict()
    loaded = get_provenance(frame)
    assert loaded is not None
    assert loaded.source == "fixture"
    assert loaded.is_approximate


def test_health_registry_circuit_and_recovery() -> None:
    registry = HostHealthRegistry(failure_threshold=2, cooldown=60)
    registry.record_failure("a", "timeout")
    assert registry.is_available("a")
    registry.record_failure("a", "timeout")
    assert not registry.is_available("a")
    registry.record_success("a", 10)
    assert registry.is_available("a")


def test_parquet_sink_rejects_invalid_table(tmp_path) -> None:
    with pytest.raises(ValueError):
        ParquetSink(tmp_path).write("../bad", pd.DataFrame({"x": [1]}))


def test_parquet_sink_reports_missing_engine(tmp_path) -> None:
    sink = ParquetSink(tmp_path)
    try:
        sink.write("bars", pd.DataFrame({"x": [1]}))
    except StorageError:
        # Environments without pyarrow/fastparquet should fail explicitly.
        pass


def test_strict_basic_daily_rejects_implicit_latest_shares() -> None:
    with pytest.raises(TdxSemanticError):
        TdxClient("127.0.0.1").get_basic_daily(
            Market.SH, "600519", 20200101, 20200102, strict_semantics=True
        )
