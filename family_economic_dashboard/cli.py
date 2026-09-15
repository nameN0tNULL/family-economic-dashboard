from __future__ import annotations

import argparse
from .engine import calculate_dashboard, load_config, load_observations, merge_observations
from .regional import load_regional_observations, summarize_regions
from .report import write_reports


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the family economic dashboard")
    parser.add_argument("--config", default="config/indicators.json")
    parser.add_argument("--data", action="append", dest="data_paths", help="Observation CSV; may be repeated")
    parser.add_argument("--regional-data", default="data/regional_observations.csv")
    parser.add_argument("--output", default="dist")
    parser.add_argument("--as-of", default=None)
    args = parser.parse_args()
    paths = args.data_paths or ["data/official_observations.csv", "data/manual_observations.csv"]
    observations = merge_observations(load_observations(path) for path in paths)
    result = calculate_dashboard(load_config(args.config), observations, args.as_of)
    regional = summarize_regions(load_regional_observations(args.regional_data))
    write_reports(result, args.output, regional)
    score = "unknown" if result.overall_score is None else f"{result.overall_score:.1f}"
    print(
        f"Built dashboard: score={score}, coverage={result.overall_coverage:.1f}%, "
        f"regional_series={len(regional.get('summaries', []))}, as_of={result.as_of}, output={args.output}"
    )


if __name__ == "__main__":
    main()
