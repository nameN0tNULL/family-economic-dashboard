from __future__ import annotations

import argparse
from .engine import calculate_dashboard, load_config, load_observations
from .report import write_reports


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the family economic dashboard")
    parser.add_argument("--config", default="config/indicators.json")
    parser.add_argument("--data", default="data/observations.csv")
    parser.add_argument("--output", default="dist")
    parser.add_argument("--as-of", default=None)
    args = parser.parse_args()
    result = calculate_dashboard(load_config(args.config), load_observations(args.data), args.as_of)
    write_reports(result, args.output)
    print(f"Built dashboard: score={result.overall_score:.1f}, as_of={result.as_of}, output={args.output}")


if __name__ == "__main__":
    main()
