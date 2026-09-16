"""Chart aggregation from Sierra settings, never inferred from timestamps or labels."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BarPeriod(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    chart_data_type: int
    intraday_bar_period_type: int
    parameters: list[int] = Field(min_length=4, max_length=4)
    historical_bar_period_type: int
    historical_days_per_bar: int


class Timeframe(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source: Literal["sierra_chart_settings"] = "sierra_chart_settings"
    scope: Literal["hosting_chart"] = "hosting_chart"
    chart_type: Literal["intraday", "historical", "unknown"]
    label: str
    seconds_per_bar: int | None = None
    raw: BarPeriod


def describe_period(period: BarPeriod) -> Timeframe:
    result = Timeframe(chart_type="unknown", label="Unknown chart period", raw=period)
    p1 = period.parameters[0]
    if period.chart_data_type == 2:  # INTRADAY_DATA, installed scconstants.h
        result.chart_type = "intraday"
        kind = period.intraday_bar_period_type
        if kind == 0 and p1 > 0:  # IBPT_DAYS_MINS_SECS: parameter 1 is seconds
            result.seconds_per_bar = p1
            for divisor, unit in [(86400, "day"), (3600, "hour"), (60, "minute"), (1, "second")]:
                if p1 % divisor == 0:
                    result.label = f"{p1 // divisor} {unit}" + ("s" if p1 // divisor != 1 else "")
                    break
        else:
            # Preserve exact variant and all parameters; these are not fixed durations.
            names = {1: "Volume", 2: "Trade count", 3: "Range", 4: "Range", 5: "Range",
                     6: "Range", 7: "Reversal", 8: "Renko", 9: "Delta volume", 10: "Flex Renko",
                     11: "Range", 12: "Price changes", 13: "Calendar months", 14: "Point and figure",
                     15: "Inverse flex Renko", 16: "Aligned Renko", 17: "Range", 18: "Custom ACSIL"}
            name = names.get(kind, "Unknown intraday")
            result.label = f"{name} bars (Sierra type {kind}; parameters {period.parameters})"
    elif period.chart_data_type == 1:  # DAILY_DATA
        result.chart_type = "historical"
        kind = period.historical_bar_period_type
        if kind == 1 and period.historical_days_per_bar > 0:
            days = period.historical_days_per_bar
            result.label = f"{days} day" + ("s" if days != 1 else "")
        else:
            result.label = {2: "Weekly", 3: "Monthly", 4: "Quarterly", 5: "Yearly"}.get(
                kind, f"Unknown historical period (Sierra type {kind})")
        # Calendar bars are not assigned a fixed elapsed duration.
    return result
