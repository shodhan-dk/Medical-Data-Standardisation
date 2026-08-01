"""CLI entry point: python -m src.main --input sample-data"""
import argparse
import json

from .pipeline import run_pipeline


def main():
    parser = argparse.ArgumentParser(description="Veritas Claims standardization pipeline")
    parser.add_argument("--input", default="sample-data", help="Folder of clinic JSON files")
    parser.add_argument("--db", default=None, help="SQLite DB path (default: veritas_claims.db)")
    args = parser.parse_args()

    stats = run_pipeline(args.input, args.db)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
