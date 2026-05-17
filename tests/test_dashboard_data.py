from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

from app.web import dashboard_data


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


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
                patch.object(dashboard_data, "refresh_fixed_calendar_events") as refresh_fixed_calendar,
                patch.object(dashboard_data, "refresh_floating_event_candidates") as refresh_candidates,
            ):
                snapshot = dashboard_data.refresh_dashboard_snapshot(
                    snapshot_path,
                    macro_history_path=macro_history_path,
                    sector_history_path=sector_history_path,
                )

            self.assertEqual(build_macro_history.call_count, 1)
            self.assertEqual(build_sector_history.call_count, 1)
            refresh_fixed_calendar.assert_called_once()
            refresh_candidates.assert_called_once()
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

    def test_market_calendar_default_window_starts_today_and_hides_empty_days(self) -> None:
        events = {
            "events": [
                {
                    "date": "2026-05-14",
                    "time_kst": f"0{index}:00",
                    "market": "US",
                    "category": "정책",
                    "title": f"event {index}",
                    "importance": "high" if index == 0 else "medium",
                    "source_name": "source",
                    "source_url": "https://example.com",
                    "why_it_matters": "market impact",
                }
                for index in range(4)
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            calendar_path = Path(temp_dir) / "market_calendar.json"
            floating_path = Path(temp_dir) / "floating_events.json"
            candidates_path = Path(temp_dir) / "floating_event_candidates.json"
            calendar_path.write_text(json.dumps(events), encoding="utf-8")
            floating_path.write_text(json.dumps({"events": []}), encoding="utf-8")
            candidates_path.write_text(json.dumps({"collection_status": {}, "candidates": []}), encoding="utf-8")

            calendar = dashboard_data.get_market_calendar(
                calendar_path=calendar_path,
                floating_events_path=floating_path,
                floating_candidates_path=candidates_path,
                today=dashboard_data.date(2026, 5, 11),
            )

        day = next(item for item in calendar["calendar_days"] if item["date"] == "2026-05-14")
        self.assertEqual(len(day["events"]), 4)
        self.assertEqual(len(day["all_events"]), 4)
        self.assertEqual(day["hidden_count"], 0)
        self.assertTrue(day["has_high"])
        self.assertEqual(day["fixed_count"], 4)
        self.assertEqual(day["floating_count"], 0)
        self.assertEqual(calendar["window"]["start"], "2026-05-11")
        self.assertEqual(calendar["window"]["end"], "2026-06-09")
        self.assertEqual([item["date"] for item in calendar["window"]["days"]], ["2026-05-14"])

    def test_market_calendar_loads_monthly_fixed_event_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            calendar_dir = Path(temp_dir) / "calendar"
            floating_dir = Path(temp_dir) / "floating_events"
            calendar_dir.mkdir()
            floating_dir.mkdir()
            (calendar_dir / "2026-05.json").write_text(
                json.dumps(
                    {
                        "month": "2026-05",
                        "events": [
                            {
                                "date": "2026-05-20",
                                "time_kst": "21:30",
                                "market": "US",
                                "category": "물가",
                                "title": "monthly event",
                                "importance": "high",
                                "source_name": "source",
                                "source_url": "https://example.com",
                                "why_it_matters": "impact",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (floating_dir / "2026-05.json").write_text(
                json.dumps(
                    {
                        "month": "2026-05",
                        "events": [
                            {
                                "date": "2026-05-21",
                                "market": "GLOBAL",
                                "category": "정책",
                                "title": "floating event",
                                "importance": "medium",
                                "status": "예정",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            calendar = dashboard_data.get_market_calendar(
                calendar_path=calendar_dir,
                floating_events_path=floating_dir,
                today=dashboard_data.date(2026, 5, 11),
                start="2026-05-20",
            )

        self.assertEqual(calendar["stats"]["fixed_total"], 1)
        self.assertEqual(calendar["stats"]["floating_total"], 0)
        self.assertEqual(calendar["month_events"][0]["title"], "monthly event")
        self.assertEqual(calendar["floating_events"], [])

    def test_market_calendar_supports_requested_window_navigation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            calendar_dir = Path(temp_dir) / "calendar"
            floating_dir = Path(temp_dir) / "floating_events"
            calendar_dir.mkdir()
            floating_dir.mkdir()
            (calendar_dir / "2026-06.json").write_text(
                json.dumps({"month": "2026-06", "events": [{"date": "2026-06-02", "title": "june"}]}),
                encoding="utf-8",
            )
            (floating_dir / "2026-06.json").write_text(json.dumps({"month": "2026-06", "events": []}), encoding="utf-8")

            calendar = dashboard_data.get_market_calendar(
                calendar_path=calendar_dir,
                floating_events_path=floating_dir,
                today=dashboard_data.date(2026, 5, 11),
                start="2026-06-01",
            )

        self.assertEqual(calendar["window"]["key"], "2026-06-01")
        self.assertEqual(calendar["window"]["previous_key"], "2026-05-02")
        self.assertEqual(calendar["window"]["next_key"], "2026-07-01")
        self.assertEqual(calendar["month_events"][0]["title"], "june")

    def test_market_calendar_loads_cross_month_window_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            calendar_dir = Path(temp_dir) / "calendar"
            calendar_dir.mkdir()
            (calendar_dir / "2026-06.json").write_text(
                json.dumps({"month": "2026-06", "events": [{"date": "2026-06-30", "title": "june event"}]}),
                encoding="utf-8",
            )
            (calendar_dir / "2026-07.json").write_text(
                json.dumps({"month": "2026-07", "events": [{"date": "2026-07-01", "title": "july event"}]}),
                encoding="utf-8",
            )

            calendar = dashboard_data.get_market_calendar(
                calendar_path=calendar_dir,
                today=dashboard_data.date(2026, 5, 17),
                start="2026-06-30",
            )

        self.assertEqual([item["title"] for item in calendar["month_events"]], ["june event", "july event"])
        self.assertEqual(calendar["window"]["start"], "2026-06-30")
        self.assertEqual(calendar["window"]["end"], "2026-07-29")

    def test_market_calendar_limits_window_navigation(self) -> None:
        calendar = dashboard_data.get_market_calendar(today=dashboard_data.date(2026, 5, 17), start="2026-11-13")
        self.assertEqual(calendar["window"]["start"], "2026-11-13")
        self.assertFalse(calendar["window"]["can_go_next"])
        self.assertTrue(calendar["window"]["can_go_previous"])

        calendar = dashboard_data.get_market_calendar(today=dashboard_data.date(2026, 5, 17), start="2026-01-01")
        self.assertEqual(calendar["window"]["start"], "2026-03-18")
        self.assertFalse(calendar["window"]["can_go_previous"])
        self.assertTrue(calendar["window"]["can_go_next"])

    def test_market_calendar_empty_window_has_no_days(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            calendar_dir = Path(temp_dir) / "calendar"
            calendar_dir.mkdir()
            (calendar_dir / "2026-05.json").write_text(json.dumps({"month": "2026-05", "events": []}), encoding="utf-8")

            calendar = dashboard_data.get_market_calendar(
                calendar_path=calendar_dir,
                today=dashboard_data.date(2026, 5, 17),
                start="2026-05-17",
            )

        self.assertEqual(calendar["window"]["days"], [])
        self.assertEqual(calendar["stats"]["fixed_total"], 0)

    def test_market_calendar_hides_floating_candidates_from_calendar_page(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            calendar_dir = Path(temp_dir) / "calendar"
            floating_dir = Path(temp_dir) / "floating_events"
            candidates_path = Path(temp_dir) / "floating_event_candidates.json"
            calendar_dir.mkdir()
            floating_dir.mkdir()
            (calendar_dir / "2026-05.json").write_text(json.dumps({"month": "2026-05", "events": []}), encoding="utf-8")
            (floating_dir / "2026-05.json").write_text(json.dumps({"month": "2026-05", "events": []}), encoding="utf-8")
            candidates_path.write_text(
                json.dumps(
                    {
                        "collection_status": {"status": "ok"},
                        "candidates": [
                            {
                                "canonical_key": "us_china_summit",
                                "title": "Trump to Meet Xi Thursday for High-Stakes US-China Summit",
                                "market": "US",
                                "axis": ["trade", "policy"],
                                "score": 31,
                                "sources": [
                                    {
                                        "domain": "cnbc",
                                        "url": "https://example.com",
                                        "seendate": "2026-05-12 01:00:00",
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            calendar = dashboard_data.get_market_calendar(
                calendar_path=calendar_dir,
                floating_events_path=floating_dir,
                floating_candidates_path=candidates_path,
                today=dashboard_data.date(2026, 5, 11),
            )

        self.assertEqual(calendar["stats"]["floating_total"], 0)
        self.assertEqual(calendar["floating_events"], [])
        self.assertEqual(calendar["calendar_days"], [])
        self.assertNotIn("2026-05-14", calendar["events_by_date"])

    def test_market_calendar_keeps_undated_candidates_out_of_grid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            calendar_dir = Path(temp_dir) / "calendar"
            floating_dir = Path(temp_dir) / "floating_events"
            candidates_path = Path(temp_dir) / "floating_event_candidates.json"
            calendar_dir.mkdir()
            floating_dir.mkdir()
            (calendar_dir / "2026-05.json").write_text(json.dumps({"month": "2026-05", "events": []}), encoding="utf-8")
            (floating_dir / "2026-05.json").write_text(json.dumps({"month": "2026-05", "events": []}), encoding="utf-8")
            candidates_path.write_text(
                json.dumps(
                    {
                        "collection_status": {"status": "ok"},
                        "candidates": [
                            {
                                "canonical_key": "federal_reserve",
                                "title": "Fed officials debate inflation path",
                                "market": "US",
                                "axis": ["rates", "policy"],
                                "score": 12,
                                "published_date": "2026-05-12",
                                "event_date": "",
                                "date_confidence": "low",
                                "sources": [{"domain": "reuters", "url": "https://example.com"}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            calendar = dashboard_data.get_market_calendar(
                calendar_path=calendar_dir,
                floating_events_path=floating_dir,
                floating_candidates_path=candidates_path,
                today=dashboard_data.date(2026, 5, 11),
            )

        self.assertEqual(calendar["floating_events"], [])
        self.assertEqual(calendar["calendar_days"], [])
        self.assertNotIn("2026-05-12", calendar["events_by_date"])

    def test_write_monthly_auto_events_preserves_manual_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            calendar_dir = Path(temp_dir) / "calendar"
            calendar_dir.mkdir()
            (calendar_dir / "2026-05.json").write_text(
                json.dumps(
                    {
                        "month": "2026-05",
                        "events": [
                            {"date": "2026-05-01", "title": "manual"},
                            {"date": "2026-05-02", "title": "old auto", "source_type": dashboard_data.AUTO_FIXED_SOURCE_TYPE},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            dashboard_data._write_monthly_auto_events(
                calendar_dir,
                2026,
                [
                    {
                        "date": "2026-05-03",
                        "title": "new auto",
                        "time_kst": "21:30",
                        "source_type": dashboard_data.AUTO_FIXED_SOURCE_TYPE,
                    }
                ],
            )

            payload = json.loads((calendar_dir / "2026-05.json").read_text(encoding="utf-8"))

        titles = [item["title"] for item in payload["events"]]
        self.assertEqual(titles, ["manual", "new auto"])

    def test_collect_census_events_tracks_selected_releases(self) -> None:
        html = """
        <table>
          <tr><td><a>Advance Monthly Sales for Retail and Food Services</a></td><td>June 17, 2026</td><td>8:30 AM</td><td>May 2026</td><td>A202606170830</td></tr>
          <tr><td><a>New Residential Construction (Building Permits, Housing Starts, and Housing Completions)</a></td><td>June 18, 2026</td><td>8:30 AM</td><td>May 2026</td><td>A202606180830</td></tr>
          <tr><td><a>Preliminary U.S. Imports for Consumption of Steel Products</a></td><td>Suspended</td><td>10:00 AM</td><td>May 2026</td><td>A202606241000</td></tr>
        </table>
        """
        with patch.object(dashboard_data.requests, "get", return_value=FakeResponse(html)):
            events = dashboard_data._collect_census_events(2026)

        self.assertEqual([event["title"] for event in events], ["미국 소매판매 - May 2026", "미국 주택착공/건축허가 - May 2026"])
        self.assertEqual(events[0]["importance"], "high")
        self.assertEqual(events[0]["time_kst"], "21:30")
        self.assertEqual(events[0]["source_name"], "Census")

    def test_collect_ism_events_generates_monthly_pmi_dates(self) -> None:
        events = dashboard_data._collect_ism_events(2026)
        january = [event for event in events if event["date"].startswith("2026-01")]

        self.assertEqual(january[0]["date"], "2026-01-02")
        self.assertEqual(january[0]["title"], "미국 ISM 제조업 PMI - January 2026")
        self.assertEqual(january[1]["date"], "2026-01-06")
        self.assertEqual(january[1]["title"], "미국 ISM 서비스업 PMI - January 2026")
        self.assertEqual(len(events), 24)

    def test_newsdata_candidates_merge_us_and_kr_canonical_events(self) -> None:
        us_article = {
            "title": "Trump Xi summit comes with high stakes for Taiwan",
            "description": "Trade and AI talks are expected.",
            "link": "https://example.com/us",
            "source_id": "example",
            "language": "english",
            "country": ["united states"],
            "pubDate": "2026-05-11 13:00:00",
        }
        kr_article = {
            "title": "미중 정상회담 앞두고 관세 협상 주목",
            "description": "반도체 수출통제도 의제로 거론된다.",
            "link": "https://example.kr/kr",
            "source_id": "examplekr",
            "language": "korean",
            "country": ["south korea"],
            "pubDate": "2026-05-11 14:00:00",
        }
        payloads = [{"results": [us_article]}, {"results": [kr_article]}]
        queries = (
            {"market": "US", "query": "Trump Xi", "language": "en", "country": "us", "canonical": "us_china_summit", "axis": ("trade", "policy")},
            {"market": "KR", "query": "미중 정상회담", "language": "ko", "country": "kr", "canonical": "us_china_summit", "axis": ("trade", "policy")},
        )

        with (
            patch.object(dashboard_data, "NEWSDATA_QUERIES", queries),
            patch.object(dashboard_data, "time") as time_module,
            patch.object(dashboard_data, "_fetch_newsdata_articles", side_effect=payloads),
        ):
            time_module.sleep.return_value = None
            result = dashboard_data._collect_newsdata_candidates("key")

        self.assertEqual(result["collection_status"]["source"], "newsdata_io")
        self.assertEqual(len(result["candidates"]), 1)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["canonical_key"], "us_china_summit")
        self.assertEqual(candidate["market"], "GLOBAL")
        self.assertEqual(candidate["hit_count"], 2)
        self.assertEqual(candidate["source_count"], 2)

    def test_newsdata_candidate_rejects_unrelated_query_results(self) -> None:
        article = {
            "title": "Roadways closed in Breaux Bridge",
            "description": "Local traffic update unrelated to monetary policy.",
            "link": "https://example.com/local",
            "source_id": "local",
            "language": "english",
            "country": ["united states"],
            "pubDate": "2026-05-11 13:00:00",
        }
        config = {
            "market": "US",
            "query": "Federal Reserve",
            "language": "en",
            "country": "us",
            "canonical": "federal_reserve",
            "axis": ("rates", "policy"),
            "required_any": ("federal reserve", "fomc", "powell", "fed rate", "rate decision"),
        }

        self.assertIsNone(dashboard_data._newsdata_article_candidate(article, config))

    def test_newsdata_candidate_rejects_class_action_noise(self) -> None:
        article = {
            "title": "DEADLINE ALERT for SMCI: Law Offices Reminds Investors of Class Actions",
            "description": "Shareholders may contact counsel about securities fraud claims.",
            "link": "https://example.com/legal",
            "source_id": "legalwire",
            "language": "english",
            "country": ["united states"],
            "pubDate": "2026-05-12 13:00:00",
        }
        config = {
            "market": "US",
            "query": "export controls",
            "language": "en",
            "country": "us",
            "canonical": "export_controls",
            "axis": ("trade", "semiconductor"),
            "required_any": ("export control", "export controls", "export restriction", "export restrictions"),
        }

        self.assertIsNone(dashboard_data._newsdata_article_candidate(article, config))

    def test_newsdata_candidate_rejects_opec_body_only_match(self) -> None:
        article = {
            "title": "Oil Up as Fading Iran Peace Hopes Spark Supply Worries",
            "description": "Traders also watched OPEC+ production comments on May 12.",
            "link": "https://example.com/oil",
            "source_id": "marketwire",
            "language": "english",
            "country": ["united states"],
            "pubDate": "2026-05-12 13:00:00",
        }
        config = {
            "market": "US",
            "query": "OPEC meeting",
            "language": "en",
            "country": "us",
            "canonical": "opec_meeting",
            "axis": ("oil", "geopolitics"),
            "required_any": ("opec meeting", "opec+", "oil output", "production cut"),
        }

        self.assertIsNone(dashboard_data._newsdata_article_candidate(article, config))

    def test_candidate_date_inference_ignores_article_dates_without_event_context(self) -> None:
        result = dashboard_data._infer_candidate_date(
            title="Oil Up as Fading Iran Peace Hopes Spark Supply Worries",
            description="The market moved on May 12 as traders weighed OPEC+ supply.",
            canonical_key="opec_meeting",
            published_date="2026-05-12",
        )

        self.assertEqual(result["event_date"], "")
        self.assertEqual(result["date_confidence"], "low")

    def test_candidate_date_inference_ignores_weekday_without_event_context(self) -> None:
        result = dashboard_data._infer_candidate_date(
            title="Oil Up as Fading Iran Peace Hopes Spark Supply Worries",
            description="Prices rose on Tuesday as traders watched OPEC+ supply.",
            canonical_key="opec_meeting",
            published_date="2026-05-12",
        )

        self.assertEqual(result["event_date"], "")
        self.assertEqual(result["date_confidence"], "low")

    def test_candidate_date_inference_uses_weekday_for_trump_xi(self) -> None:
        result = dashboard_data._infer_candidate_date(
            title="Trump to Meet Xi Thursday for High-Stakes US-China Summit",
            description="",
            canonical_key="us_china_summit",
            published_date="2026-05-12",
        )

        self.assertEqual(result["event_date"], "2026-05-14")
        self.assertEqual(result["event_end_date"], "2026-05-15")
        self.assertEqual(result["date_confidence"], "high")

    def test_candidate_date_inference_uses_explicit_range(self) -> None:
        result = dashboard_data._infer_candidate_date(
            title="Trump-Xi summit set for May 14-15",
            description="",
            canonical_key="us_china_summit",
            published_date="2026-05-12",
        )

        self.assertEqual(result["event_date"], "2026-05-14")
        self.assertEqual(result["event_end_date"], "2026-05-15")
        self.assertEqual(result["date_confidence"], "high")

    def test_refresh_floating_candidates_keeps_previous_on_newsdata_failure(self) -> None:
        previous = {
            "collection_status": {"status": "ok"},
            "candidates": [{"canonical_key": "us_china_summit", "title": "old"}],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            candidates_path = Path(temp_dir) / "floating_event_candidates.json"
            candidates_path.write_text(json.dumps(previous), encoding="utf-8")

            with patch.object(dashboard_data, "_collect_news_candidates", side_effect=RuntimeError("NewsData.io failed")):
                result = dashboard_data.refresh_floating_event_candidates(candidates_path)

            saved = json.loads(candidates_path.read_text(encoding="utf-8"))

        self.assertEqual(result["collection_status"]["status"], "failed")
        self.assertIn("NewsData.io failed", result["collection_status"]["message"])
        self.assertEqual(result["candidates"], previous["candidates"])
        self.assertEqual(saved, result)

    def test_refresh_floating_candidates_keeps_previous_on_rate_limit_payload(self) -> None:
        previous = {
            "collection_status": {"status": "ok"},
            "candidates": [{"canonical_key": "us_china_summit", "title": "old"}],
        }
        rate_limited = {
            "collection_status": {
                "status": "empty",
                "source": "newsdata_io",
                "query_count": 0,
                "errors": [{"query": "Trump Xi", "error": "RateLimitExceeded"}],
            },
            "candidates": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            candidates_path = Path(temp_dir) / "floating_event_candidates.json"
            candidates_path.write_text(json.dumps(previous), encoding="utf-8")

            with patch.object(dashboard_data, "_collect_news_candidates", return_value=rate_limited):
                result = dashboard_data.refresh_floating_event_candidates(candidates_path)

            saved = json.loads(candidates_path.read_text(encoding="utf-8"))

        self.assertEqual(result["collection_status"]["status"], "failed")
        self.assertIn("kept previous candidates", result["collection_status"]["message"])
        self.assertEqual(result["candidates"], previous["candidates"])
        self.assertEqual(saved, result)


if __name__ == "__main__":
    unittest.main()
