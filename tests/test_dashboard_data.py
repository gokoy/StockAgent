from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

from app.web import dashboard_data


class DashboardDataTests(unittest.TestCase):
    def test_refresh_dashboard_snapshot_reuses_built_histories(self) -> None:
        macro_history = {"generated_at": "test", "years": 5, "indicators": []}
        sector_history = {"generated_at": "test", "years": 5, "sectors": []}
        macro_dashboard = {
            "as_of": "test",
            "decision": {"score": 50},
            "ai_summary": {"source": "fallback"},
            "groups": {},
            "failed_count": 0,
        }
        sector_dashboard = {
            "market": "US",
            "benchmark": "S&P 500",
            "as_of": "test",
            "leaders": [],
            "laggards": [],
            "flow_summary": {},
            "comparison_chart": {},
            "sectors": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "dashboard_snapshot.json"
            macro_history_path = Path(temp_dir) / "macro_history.json"
            sector_history_path = Path(temp_dir) / "sector_history.json"

            with (
                patch.object(dashboard_data, "build_macro_history", return_value=macro_history) as build_macro_history,
                patch.object(dashboard_data, "build_sector_history", return_value=sector_history) as build_sector_history,
                patch.object(dashboard_data, "_get_macro_dashboard_live", return_value=macro_dashboard) as get_macro,
                patch.object(dashboard_data, "_get_sector_dashboard_live", return_value=sector_dashboard) as get_sector,
            ):
                snapshot = dashboard_data.refresh_dashboard_snapshot(
                    snapshot_path,
                    macro_history_path=macro_history_path,
                    sector_history_path=sector_history_path,
                )

            self.assertEqual(build_macro_history.call_count, 1)
            self.assertEqual(build_sector_history.call_count, 1)
            get_macro.assert_called_once_with(macro_history=macro_history)
            get_sector.assert_has_calls(
                [
                    call("US", sector_history=sector_history),
                    call("KR", sector_history=sector_history),
                ]
            )
            self.assertEqual(snapshot["macro"], macro_dashboard)
            self.assertEqual(json.loads(snapshot_path.read_text(encoding="utf-8")), snapshot)
            self.assertEqual(json.loads(macro_history_path.read_text(encoding="utf-8")), macro_history)
            self.assertEqual(json.loads(sector_history_path.read_text(encoding="utf-8")), sector_history)

    def test_window_return_uses_value_before_window(self) -> None:
        series = dashboard_data.pd.Series([100.0, 105.0, 110.0])

        self.assertEqual(dashboard_data._window_return(series, 3), 0.0)
        self.assertAlmostEqual(dashboard_data._window_return(series, 2), 10.0)

    def test_percentile_rank_counts_values_below_or_equal(self) -> None:
        result = dashboard_data._percentile_rank([1.0, 2.0, 3.0, 4.0], 3.0)

        self.assertEqual(result, 75.0)

    def test_signal_classification_respects_series_kind(self) -> None:
        self.assertEqual(dashboard_data._classify_signal("risk_on", 1.0, 1.0), "매수 우세")
        self.assertEqual(dashboard_data._classify_signal("risk_on", -1.0, -1.0), "매도 우세")
        self.assertEqual(dashboard_data._classify_signal("risk_off", 1.0, 1.0), "매수 부담 증가")
        self.assertEqual(dashboard_data._classify_signal("risk_off", -1.0, -1.0), "매수 부담 감소")
        self.assertEqual(dashboard_data._classify_signal("neutral", 0.01, 0.01), "관망")

    def test_sector_history_stats_returns_percentile_and_zone(self) -> None:
        history_points = []
        for index in range(22):
            history_points.append(
                {
                    "date": f"2026-01-{index + 1:02d}",
                    "sector": 100.0 + index,
                    "benchmark": 100.0,
                }
            )

        stats = dashboard_data._sector_history_stats(history_points, current_relative_strength=19.9)

        self.assertEqual(stats["lookback_years"], dashboard_data.SECTOR_HISTORY_YEARS)
        self.assertEqual(stats["observations"], 2)
        self.assertEqual(stats["percentile"], 50.0)
        self.assertEqual(stats["zone"], "5년 기준 보통 구간")


if __name__ == "__main__":
    unittest.main()
