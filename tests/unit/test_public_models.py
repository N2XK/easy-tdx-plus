from easy_tdx import (
    FundFlow,
    IndexInfo,
    MarketStat,
    SecurityFeature,
    VolumeProfile,
)
from easy_tdx.models import (
    AuctionPoint,
    HistoricalFundFlow,
    MinuteAuxPoint,
    SparklineSeries,
    TdxBjCode,
)


def test_public_model_exports() -> None:
    assert all(
        model is not None
        for model in (
            AuctionPoint,
            FundFlow,
            HistoricalFundFlow,
            IndexInfo,
            MarketStat,
            MinuteAuxPoint,
            SecurityFeature,
            SparklineSeries,
            TdxBjCode,
            VolumeProfile,
        )
    )
