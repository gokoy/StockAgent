from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.web.dashboard_data import ROOT_DIR, get_macro_dashboard, get_sector_dashboard


TEMPLATE_DIR = ROOT_DIR / "app" / "web" / "templates"
STATIC_DIR = ROOT_DIR / "app" / "web" / "static"
SNAPSHOT_PATH = ROOT_DIR / "data" / "web" / "dashboard_snapshot.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build GitHub Pages static site.")
    parser.add_argument("--output", type=Path, default=ROOT_DIR / "docs", help="Output directory for GitHub Pages.")
    args = parser.parse_args()
    build_static_site(args.output)


def build_static_site(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")
    _copy_static_assets(output_dir)
    _copy_dashboard_data(output_dir)

    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(("html", "xml")),
    )

    macro_dashboard = get_macro_dashboard()
    us_dashboard = get_sector_dashboard("US")
    kr_dashboard = get_sector_dashboard("KR")

    _write_page(
        output_dir / "index.html",
        env.get_template("macro.html"),
        _context(
            active_page="macro",
            dashboard=macro_dashboard,
            static_prefix=".",
            macro_href="./",
            sectors_href="sectors/",
        ),
    )
    _write_page(
        output_dir / "macro" / "index.html",
        env.get_template("macro.html"),
        _context(
            active_page="macro",
            dashboard=macro_dashboard,
            static_prefix="..",
            macro_href="./",
            sectors_href="../sectors/",
        ),
    )
    _write_page(
        output_dir / "sectors" / "index.html",
        env.get_template("sectors.html"),
        _context(
            active_page="sectors",
            dashboard=us_dashboard,
            static_prefix="..",
            macro_href="../macro/",
            sectors_href="./",
            sector_us_href="./",
            sector_kr_href="kr/",
        ),
    )
    _write_page(
        output_dir / "sectors" / "kr" / "index.html",
        env.get_template("sectors.html"),
        _context(
            active_page="sectors",
            dashboard=kr_dashboard,
            static_prefix="../..",
            macro_href="../../macro/",
            sectors_href="../",
            sector_us_href="../",
            sector_kr_href="./",
        ),
    )


def _context(static_prefix: str, **kwargs: Any) -> dict[str, Any]:
    return {
        **kwargs,
        "static_styles_href": f"{static_prefix}/static/styles.css?v=20260429-7",
        "static_script_href": f"{static_prefix}/static/dashboard.js?v=20260429-7",
    }


def _write_page(path: Path, template: Any, context: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(template.render(**context), encoding="utf-8")


def _copy_static_assets(output_dir: Path) -> None:
    target = output_dir / "static"
    target.mkdir(parents=True, exist_ok=True)
    for source in STATIC_DIR.iterdir():
        if source.is_file():
            shutil.copy2(source, target / source.name)


def _copy_dashboard_data(output_dir: Path) -> None:
    if not SNAPSHOT_PATH.exists():
        return
    target = output_dir / "data" / "dashboard_snapshot.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
