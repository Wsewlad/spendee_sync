"""Training script for the ML categorizer.

Usage:
    python -m spendee_sync.train --input spendee_export.csv
    python -m spendee_sync.train --input spendee_export.csv --model ml_model.joblib
    python -m spendee_sync.train --input spendee_export.csv --threshold 0.8
"""
from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train the ML categorizer on a Spendee export CSV.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input",
        required=True,
        metavar="CSV_PATH",
        help="Path to the Spendee export CSV file (must have 'Note' and 'Category name' columns).",
    )
    parser.add_argument(
        "--model",
        default="ml_model.joblib",
        metavar="MODEL_PATH",
        help="Path where the trained model will be saved (default: ml_model.joblib).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.7,
        metavar="FLOAT",
        help="Confidence threshold for ML predictions at inference time (default: 0.7).",
    )

    args = parser.parse_args()

    from spendee_sync.utils.ml_categorizer import MLCategorizer

    categorizer = MLCategorizer(model_path=args.model, confidence_threshold=args.threshold)

    print(f"Training on: {args.input}")
    try:
        stats = categorizer.train(args.input)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"  Samples:      {stats['samples']}")
    print(f"  Categories:   {stats['classes']}")
    print(f"  Train accuracy: {stats['accuracy']:.1%}")
    if stats.get("cv_accuracy") is not None:
        print(f"  CV accuracy:    {stats['cv_accuracy']:.1%}")

    categorizer.save()
    print(f"Model saved to: {args.model}")
    print(f"Confidence threshold: {args.threshold}")


if __name__ == "__main__":
    main()
