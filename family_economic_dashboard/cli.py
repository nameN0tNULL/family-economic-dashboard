from __future__ import annotations

import argparse
from .city_vitality import enrich_reports as enrich_city_reports, load_city_population, summarize_city_population
from .engine import calculate_dashboard, load_config, load_observations, merge_observations
from .housing import enrich_reports as enrich_housing_reports, load_city_prices, summarize_housing
from .recruitment import (
    enrich_reports as enrich_recruitment_reports,
    load_market,
    load_search_snapshots,
    search_snapshots_to_observations,
    summarize_recruitment,
)
from .regional import load_regional_observations, summarize_regions
from .report import write_reports


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the family economic dashboard")
    parser.add_argument("--config", default="config/indicators.json")
    parser.add_argument("--data", action="append", dest="data_paths", help="Observation CSV; may be repeated")
    parser.add_argument("--regional-data", default="data/regional_observations.csv")
    parser.add_argument("--housing-city-prices", default="data/housing_city_prices.csv")
    parser.add_argument("--housing-observations", default="data/housing_observations.csv")
    parser.add_argument("--city-population", default="data/city_population.csv")
    parser.add_argument("--recruitment-market", default="data/recruitment_market.csv")
    parser.add_argument("--recruitment-searches", default="data/recruitment_searches.csv")
    parser.add_argument("--output", default="dist")
    parser.add_argument("--as-of", default=None)
    args = parser.parse_args()

    paths = args.data_paths or [
        "data/official_observations.csv",
        args.housing_observations,
        "data/manual_observations.csv",
    ]
    search_rows = load_search_snapshots(args.recruitment_searches)
    observations = merge_observations(
        [load_observations(path) for path in paths] + [search_snapshots_to_observations(search_rows)]
    )
    result = calculate_dashboard(load_config(args.config), observations, args.as_of)
    regional = summarize_regions(load_regional_observations(args.regional_data))
    housing = summarize_housing(load_city_prices(args.housing_city_prices))
    city = summarize_city_population(load_city_population(args.city_population))
    recruitment = summarize_recruitment(load_market(args.recruitment_market), search_rows)

    write_reports(result, args.output, regional)
    enrich_housing_reports(args.output, housing)
    enrich_city_reports(args.output, city)
    enrich_recruitment_reports(args.output, recruitment)

    score = "unknown" if result.overall_score is None else f"{result.overall_score:.1f}"
    print(
        f"Built dashboard: score={score}, coverage={result.overall_coverage:.1f}%, "
        f"regional_series={len(regional.get('summaries', []))}, "
        f"housing_series={len(housing.get('summaries', []))}, "
        f"city_population={len(city.get('cities', []))}, "
        f"recruitment_regions={len(recruitment.get('market_summaries', []))}, "
        f"as_of={result.as_of}, output={args.output}"
    )


if __name__ == "__main__":
    main()
