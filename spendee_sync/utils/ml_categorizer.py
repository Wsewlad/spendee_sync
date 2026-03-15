from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pandas as pd


class MLCategorizer:
    """ML-based transaction categorizer using TF-IDF + logistic regression.

    Trains on a Spendee export CSV where the 'Note' column contains the
    transaction description and 'Category name' contains the label.
    """

    def __init__(self, model_path: str = "ml_model.joblib", confidence_threshold: float = 0.7) -> None:
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self._pipeline: Optional[object] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def train(self, labeled_csv_path: str) -> dict:
        """Train on a Spendee export CSV.

        Expected columns: Date, Type, Category name, Amount, Note, Labels
        'Note' column is used as the description text.
        'Category name' column is used as the label.

        Args:
            labeled_csv_path: Path to the Spendee export CSV file.

        Returns:
            dict with training statistics: samples, classes, accuracy, cv_accuracy.
        """
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import cross_val_score
        from sklearn.pipeline import Pipeline

        df = pd.read_csv(labeled_csv_path)

        # Validate required columns
        if "Note" not in df.columns or "Category name" not in df.columns:
            raise ValueError(
                "CSV must contain 'Note' and 'Category name' columns. "
                f"Found: {list(df.columns)}"
            )

        # Drop rows with missing values in required columns
        df = df.dropna(subset=["Note", "Category name"])
        df = df[df["Note"].str.strip() != ""]
        df = df[df["Category name"].str.strip() != ""]

        if len(df) == 0:
            raise ValueError("No valid labeled samples found in CSV after cleaning.")

        X = df["Note"].astype(str).tolist()
        y = df["Category name"].astype(str).tolist()

        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(
                ngram_range=(1, 2),
                min_df=1,
                max_features=10_000,
                sublinear_tf=True,
            )),
            ("clf", LogisticRegression(
                max_iter=1000,
                C=1.0,
                solver="lbfgs",
            )),
        ])

        # Cross-validation score (only when enough samples per class)
        cv_accuracy: Optional[float] = None
        from collections import Counter as _Counter
        n_classes = len(set(y))
        min_class_count = min(_Counter(y).values())
        cv_folds = min(5, min_class_count)
        if cv_folds >= 2:
            scores = cross_val_score(pipeline, X, y, cv=cv_folds, scoring="accuracy")
            cv_accuracy = float(scores.mean())

        # Train on full dataset
        pipeline.fit(X, y)
        self._pipeline = pipeline

        # In-sample accuracy
        train_preds = pipeline.predict(X)
        in_sample_accuracy = float(sum(p == t for p, t in zip(train_preds, y)) / len(y))

        stats = {
            "samples": len(X),
            "classes": len(set(y)),
            "accuracy": in_sample_accuracy,
            "cv_accuracy": cv_accuracy,
        }
        return stats

    def predict(self, description: str) -> tuple[str | None, float]:
        """Predict category for a transaction description.

        Args:
            description: Transaction description text.

        Returns:
            Tuple of (category, confidence). Returns (None, 0.0) if model is
            not loaded or description is empty.
        """
        if self._pipeline is None:
            return None, 0.0

        if not description or not description.strip():
            return None, 0.0

        import numpy as np

        proba = self._pipeline.predict_proba([description])[0]
        max_idx = int(np.argmax(proba))
        confidence = float(proba[max_idx])
        category = self._pipeline.classes_[max_idx]
        return str(category), confidence

    def is_trained(self) -> bool:
        """Return True if a model is currently loaded/trained."""
        return self._pipeline is not None

    def save(self) -> None:
        """Save the trained model to disk using joblib.

        Raises:
            RuntimeError: If no model has been trained yet.
        """
        if self._pipeline is None:
            raise RuntimeError("No trained model to save. Call train() first.")

        import joblib

        path = Path(self.model_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._pipeline, path)

    def load(self) -> bool:
        """Load a trained model from disk.

        Returns:
            True if the model was loaded successfully, False if the file does
            not exist.
        """
        import joblib

        path = Path(self.model_path)
        if not path.exists():
            return False

        self._pipeline = joblib.load(path)
        return True
