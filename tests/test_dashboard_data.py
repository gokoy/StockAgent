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

    def test_macro_decision_uses_standardized_factor_model(self) -> None:
        def indicator(item_id: str, name: str, kind: str, values: list[float]) -> dict[str, object]:
            return {
                "id": item_id,
                "name": name,
                "kind": kind,
                "latest_date": "2026-05-05",
                "change_pct": 1.0,
                "change_abs": 1.0,
                "signal": "매수 우세",
                "history_stats": {"percentile": 80.0},
                "points": [
                    {"date": f"2026-01-{index + 1:02d}", "value": value}
                    for index, value in enumerate(values[:31])
                ],
            }

        decision = dashboard_data._build_macro_decision(
            [
                indicator("sp500", "S&P 500", "risk_on", [100.0 + index for index in range(31)]),
                indicator("vix", "VIX", "risk_off", [20.0 + index for index in range(31)]),
            ]
        )

        self.assertEqual(decision["score_model"], "standardized_factor_v2")
        factor_scores = {item["id"]: item for item in decision["factor_scores"]}
        self.assertGreater(factor_scores["equity_momentum"]["points"], 0)
        self.assertLess(factor_scores["volatility"]["points"], 0)

    def test_build_macro_history_preserves_previous_points_on_fetch_failure(self) -> None:
        spec = dashboard_data.IndicatorSpec(
            id="dgs10",
            name="미국 10년 금리",
            group="금리/할인율",
            source="fred",
            symbol="DGS10",
            unit="%",
            kind="risk_off",
        )
        previous_points = [{"date": "2026-05-01", "value": 4.5}]
        previous_history = {
            "generated_at": "old",
            "years": 5,
            "indicators": [
                {
                    "id": "dgs10",
                    "name": "미국 10년 금리",
                    "group": "금리/할인율",
                    "kind": "risk_off",
                    "unit": "%",
                    "points": previous_points,
                }
            ],
        }

        with (
            patch.object(dashboard_data, "MACRO_SPECS", (spec,)),
            patch.object(dashboard_data, "_fetch_indicator_series", side_effect=TimeoutError("timed out")),
        ):
            history = dashboard_data.build_macro_history(previous_history=previous_history)

        item = history["indicators"][0]
        self.assertEqual(item["points"], previous_points)
        self.assertTrue(item["stale"])
        self.assertIn("timed out", item["error"])

    def test_macro_dashboard_uses_history_fallback_for_failed_indicator(self) -> None:
        spec = dashboard_data.IndicatorSpec(
            id="dgs10",
            name="미국 10년 금리",
            group="금리/할인율",
            source="fred",
            symbol="DGS10",
            unit="%",
            kind="risk_off",
        )
        macro_history = {
            "generated_at": "old",
            "years": 5,
            "indicators": [
                {
                    "id": "dgs10",
                    "name": "미국 10년 금리",
                    "group": "금리/할인율",
                    "kind": "risk_off",
                    "unit": "%",
                    "points": [
                        {"date": "2026-05-01", "value": 4.5},
                        {"date": "2026-05-02", "value": 4.4},
                    ],
                }
            ],
        }

        with (
            patch.object(dashboard_data, "MACRO_SPECS", (spec,)),
            patch.object(dashboard_data, "_fetch_indicator_series", side_effect=TimeoutError("timed out")),
        ):
            dashboard = dashboard_data._get_macro_dashboard_live(macro_history=macro_history)

        item = dashboard["groups"]["금리/할인율"][0]
        self.assertEqual(item["value"], 4.4)
        self.assertTrue(item["stale"])
        self.assertEqual(dashboard["failed_count"], 1)
        self.assertEqual(dashboard["failed_indicators"][0]["name"], "미국 10년 금리")

    def test_macro_score_history_rebuilds_scores_from_history_points(self) -> None:
        spec = dashboard_data.IndicatorSpec(
            id="sp500",
            name="S&P 500",
            group="주식 위험선호",
            source="yahoo",
            symbol="^GSPC",
            kind="risk_on",
        )
        macro_history = {
            "generated_at": "test",
            "years": 5,
            "indicators": [
                {
                    "id": "sp500",
                    "name": "S&P 500",
                    "group": "주식 위험선호",
                    "kind": "risk_on",
                    "unit": "pt",
                    "points": [
                        {"date": f"2026-01-{index + 1:02d}", "value": 100.0 + index}
                        for index in range(28)
                    ],
                }
            ],
        }

        with patch.object(dashboard_data, "MACRO_SPECS", (spec,)):
            score_history = dashboard_data._build_macro_score_history(macro_history)

        self.assertEqual(len(score_history), 28)
        self.assertEqual(score_history[-1]["date"], "2026-01-28")
        self.assertIn("score", score_history[-1])
        self.assertEqual(score_history[-1]["indicator_count"], 1)

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
