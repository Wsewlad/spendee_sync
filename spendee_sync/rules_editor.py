"""Interactive CLI editor for category and label rules.

Usage:
    python -m spendee_sync.rules_editor
    python -m spendee_sync.rules_editor --categories path/to/categories.json --labels path/to/labels.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Optional rich support
# ---------------------------------------------------------------------------
try:
    from rich.console import Console
    from rich.table import Table

    _RICH = True
    _console = Console()
except ImportError:
    _RICH = False
    _console = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------
_UTILS_DIR = Path(__file__).parent / "utils"
DEFAULT_CATEGORIES_PATH = _UTILS_DIR / "categories.json"
DEFAULT_LABELS_PATH = _UTILS_DIR / "labels_keywords.json"


# ---------------------------------------------------------------------------
# Helper I/O
# ---------------------------------------------------------------------------

def _print(msg: str = "") -> None:
    if _RICH:
        _console.print(msg)
    else:
        print(msg)


def _input(prompt: str) -> str:
    """Thin wrapper around input() that works with rich present or absent."""
    return input(prompt)


def _parse_int_list(raw: str) -> list[int]:
    """Parse a comma-separated string of integers, ignoring blanks."""
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    result: list[int] = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            _print(f"  [yellow]Warning:[/yellow] '{p}' is not a valid integer, skipping."
                   if _RICH else f"  Warning: '{p}' is not a valid integer, skipping.")
    return result


def _parse_str_list(raw: str) -> list[str]:
    """Parse a comma-separated string of values, ignoring blanks."""
    return [p.strip() for p in raw.split(",") if p.strip()]


def _confirm(prompt: str) -> bool:
    """Ask a yes/no question and return True for yes."""
    answer = _input(f"{prompt} [y/N]: ").strip().lower()
    return answer in ("y", "yes")


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _show_categories(categories: dict[str, dict[str, Any]]) -> None:
    if not categories:
        _print("  (no categories)")
        return

    if _RICH:
        table = Table(title="Categories", show_lines=True)
        table.add_column("#", style="dim", justify="right")
        table.add_column("Name", style="bold cyan")
        table.add_column("MCC codes", style="yellow")
        table.add_column("Keywords", style="green")
        for idx, (name, rules) in enumerate(categories.items(), 1):
            mcc = rules.get("mcc", [])
            kw = rules.get("keywords", [])
            table.add_row(
                str(idx),
                name,
                ", ".join(str(m) for m in mcc) if mcc else "(none)",
                f"{len(kw)} keyword(s): {', '.join(kw[:5])}{'…' if len(kw) > 5 else ''}" if kw else "(none)",
            )
        _console.print(table)
    else:
        print(f"\n{'#':<4} {'Name':<30} {'MCCs':<30} {'Keywords'}")
        print("-" * 90)
        for idx, (name, rules) in enumerate(categories.items(), 1):
            mcc = rules.get("mcc", [])
            kw = rules.get("keywords", [])
            mcc_str = ", ".join(str(m) for m in mcc) if mcc else "(none)"
            kw_str = f"{len(kw)} kw" if kw else "(none)"
            print(f"{idx:<4} {name:<30} {mcc_str:<30} {kw_str}")
        print()


def _show_labels(labels: dict[str, list[str]]) -> None:
    if not labels:
        _print("  (no labels)")
        return

    if _RICH:
        table = Table(title="Labels", show_lines=True)
        table.add_column("#", style="dim", justify="right")
        table.add_column("Label", style="bold magenta")
        table.add_column("Keywords", style="green")
        for idx, (name, kws) in enumerate(labels.items(), 1):
            table.add_row(str(idx), name, ", ".join(kws) if kws else "(none)")
        _console.print(table)
    else:
        print(f"\n{'#':<4} {'Label':<30} {'Keywords'}")
        print("-" * 70)
        for idx, (name, kws) in enumerate(labels.items(), 1):
            print(f"{idx:<4} {name:<30} {', '.join(kws) if kws else '(none)'}")
        print()


# ---------------------------------------------------------------------------
# Editor state
# ---------------------------------------------------------------------------

class RulesEditor:
    def __init__(self, categories_path: Path, labels_path: Path) -> None:
        self.categories_path = categories_path
        self.labels_path = labels_path
        self.categories: dict[str, dict[str, Any]] = {}
        self.labels: dict[str, list[str]] = {}
        self.dirty = False
        self._load()

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load both JSON files into memory."""
        if self.categories_path.exists():
            try:
                with open(self.categories_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.categories = data
                    _print(f"Loaded {len(self.categories)} categories from {self.categories_path}")
                else:
                    _print(f"Warning: {self.categories_path} has unexpected format, starting empty.")
            except Exception as exc:
                _print(f"Error loading categories: {exc}")
        else:
            _print(f"Categories file not found: {self.categories_path}. Starting with empty data.")

        if self.labels_path.exists():
            try:
                with open(self.labels_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.labels = data
                    _print(f"Loaded {len(self.labels)} labels from {self.labels_path}")
                else:
                    _print(f"Warning: {self.labels_path} has unexpected format, starting empty.")
            except Exception as exc:
                _print(f"Error loading labels: {exc}")
        else:
            _print(f"Labels file not found: {self.labels_path}. Starting with empty data.")

    def save(self) -> None:
        """Write both JSON files back to disk."""
        try:
            with open(self.categories_path, "w", encoding="utf-8") as f:
                json.dump(self.categories, f, indent=2, ensure_ascii=False)
            with open(self.labels_path, "w", encoding="utf-8") as f:
                json.dump(self.labels, f, indent=2, ensure_ascii=False)
            self.dirty = False
            _print("[green]Saved successfully.[/green]" if _RICH else "Saved successfully.")
        except Exception as exc:
            _print(f"[red]Error saving:[/red] {exc}" if _RICH else f"Error saving: {exc}")

    # ------------------------------------------------------------------
    # Category operations
    # ------------------------------------------------------------------

    def list_categories(self) -> None:
        _show_categories(self.categories)

    def add_category(self) -> None:
        name = _input("Category name: ").strip()
        if not name:
            _print("Aborted (empty name).")
            return
        if name in self.categories:
            _print(f"Category '{name}' already exists. Use Edit to modify it.")
            return
        mcc_raw = _input("MCC codes (comma-separated, or leave blank): ").strip()
        kw_raw = _input("Keywords (comma-separated, or leave blank): ").strip()
        self.categories[name] = {
            "mcc": _parse_int_list(mcc_raw) if mcc_raw else [],
            "keywords": _parse_str_list(kw_raw) if kw_raw else [],
        }
        self.dirty = True
        _print(f"[green]Added category:[/green] {name}" if _RICH else f"Added category: {name}")

    def edit_category(self) -> None:
        if not self.categories:
            _print("No categories to edit.")
            return
        _show_categories(self.categories)
        name = _input("Enter category name to edit: ").strip()
        if name not in self.categories:
            _print(f"Category '{name}' not found.")
            return
        current = self.categories[name]
        current_mcc = ", ".join(str(m) for m in current.get("mcc", []))
        current_kw = ", ".join(current.get("keywords", []))
        _print(f"Current MCCs   : {current_mcc or '(none)'}")
        _print(f"Current keywords: {current_kw or '(none)'}")
        mcc_raw = _input(f"New MCC codes (leave blank to keep '{current_mcc or 'none'}'): ").strip()
        kw_raw = _input(f"New keywords (leave blank to keep '{current_kw or 'none'}'): ").strip()
        if mcc_raw:
            current["mcc"] = _parse_int_list(mcc_raw)
        if kw_raw:
            current["keywords"] = _parse_str_list(kw_raw)
        self.categories[name] = current
        self.dirty = True
        _print(f"[green]Updated category:[/green] {name}" if _RICH else f"Updated category: {name}")

    def remove_category(self) -> None:
        if not self.categories:
            _print("No categories to remove.")
            return
        _show_categories(self.categories)
        name = _input("Enter category name to remove: ").strip()
        if name not in self.categories:
            _print(f"Category '{name}' not found.")
            return
        if _confirm(f"Remove category '{name}'?"):
            del self.categories[name]
            self.dirty = True
            _print(f"[red]Removed category:[/red] {name}" if _RICH else f"Removed category: {name}")
        else:
            _print("Cancelled.")

    # ------------------------------------------------------------------
    # Label operations
    # ------------------------------------------------------------------

    def list_labels(self) -> None:
        _show_labels(self.labels)

    def add_label(self) -> None:
        name = _input("Label name: ").strip()
        if not name:
            _print("Aborted (empty name).")
            return
        if name in self.labels:
            _print(f"Label '{name}' already exists. Use Edit to modify it.")
            return
        kw_raw = _input("Keywords (comma-separated): ").strip()
        self.labels[name] = _parse_str_list(kw_raw) if kw_raw else []
        self.dirty = True
        _print(f"[green]Added label:[/green] {name}" if _RICH else f"Added label: {name}")

    def edit_label(self) -> None:
        if not self.labels:
            _print("No labels to edit.")
            return
        _show_labels(self.labels)
        name = _input("Enter label name to edit: ").strip()
        if name not in self.labels:
            _print(f"Label '{name}' not found.")
            return
        current_kw = ", ".join(self.labels[name])
        _print(f"Current keywords: {current_kw or '(none)'}")
        kw_raw = _input(f"New keywords (leave blank to keep '{current_kw or 'none'}'): ").strip()
        if kw_raw:
            self.labels[name] = _parse_str_list(kw_raw)
        self.dirty = True
        _print(f"[green]Updated label:[/green] {name}" if _RICH else f"Updated label: {name}")

    def remove_label(self) -> None:
        if not self.labels:
            _print("No labels to remove.")
            return
        _show_labels(self.labels)
        name = _input("Enter label name to remove: ").strip()
        if name not in self.labels:
            _print(f"Label '{name}' not found.")
            return
        if _confirm(f"Remove label '{name}'?"):
            del self.labels[name]
            self.dirty = True
            _print(f"[red]Removed label:[/red] {name}" if _RICH else f"Removed label: {name}")
        else:
            _print("Cancelled.")

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def preview(self) -> None:
        """Preview categorization for a test description string."""
        desc = _input("Enter test description: ").strip()
        if not desc:
            _print("No description provided.")
            return

        mcc_raw = _input("MCC code (optional, press Enter to skip): ").strip()
        mcc_code = 0
        if mcc_raw:
            try:
                mcc_code = int(mcc_raw)
            except ValueError:
                _print("Invalid MCC, using 0.")

        # Build rules from current in-memory data
        mcc_rules: dict[str, list[int]] = {}
        keyword_data: dict[str, list[str]] = {}
        for cat_name, cat_rules in self.categories.items():
            if not isinstance(cat_rules, dict):
                continue
            mcc_list = cat_rules.get("mcc", [])
            if isinstance(mcc_list, list) and mcc_list:
                mcc_rules[cat_name] = [int(c) for c in mcc_list]
            kw_list = cat_rules.get("keywords", [])
            if isinstance(kw_list, list) and kw_list:
                keyword_data[cat_name] = kw_list

        # Compile keyword patterns (inline, to avoid import side-effects)
        patterns: list[tuple[re.Pattern[str], str]] = []
        for cat_name, words in keyword_data.items():
            normalized = [str(w).strip().lower() for w in words if isinstance(w, (str, bytes))]
            normalized = [w for w in normalized if w]
            if not normalized:
                continue
            escaped = [re.escape(w) for w in normalized]
            pat = re.compile(rf"\b(?:{'|'.join(escaped)})\b", re.IGNORECASE)
            patterns.append((pat, cat_name))

        # Determine category using same priority as categorize_transaction
        category = None

        # Priority 1 (as in categorizer.py): keyword patterns
        desc_lower = desc.lower()
        for pat, cat_name in patterns:
            if pat.search(desc_lower):
                category = cat_name
                break

        # Priority 2: MCC lookup
        if category is None and mcc_code and mcc_rules:
            for cat_name, codes in mcc_rules.items():
                if mcc_code in codes:
                    category = cat_name
                    break

        # Priority 3: fallback
        if category is None:
            category = "Income (fallback)" if mcc_code == 0 else "Other (fallback)"

        # Determine labels
        assigned_labels: list[str] = []
        for label_name, label_kws in self.labels.items():
            if any(kw and kw.lower() in desc_lower for kw in label_kws):
                assigned_labels.append(label_name)

        if _RICH:
            result_table = Table(title=f"Preview for: {desc!r}", show_lines=True)
            result_table.add_column("Field", style="bold")
            result_table.add_column("Value")
            result_table.add_row("Description", desc)
            result_table.add_row("MCC", str(mcc_code) if mcc_code else "(none)")
            result_table.add_row("Category", f"[cyan]{category}[/cyan]")
            result_table.add_row("Labels", f"[magenta]{', '.join(assigned_labels)}[/magenta]" if assigned_labels else "(none)")
            _console.print(result_table)
        else:
            print(f"\n--- Preview for: {desc!r} ---")
            print(f"  MCC      : {mcc_code if mcc_code else '(none)'}")
            print(f"  Category : {category}")
            print(f"  Labels   : {', '.join(assigned_labels) if assigned_labels else '(none)'}")
            print()

    # ------------------------------------------------------------------
    # Main menu loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        menu = (
            "\n[bold]Category & Label Editor[/bold]\n"
            "  [1] List categories\n"
            "  [2] Add category\n"
            "  [3] Edit category\n"
            "  [4] Remove category\n"
            "  [5] List labels\n"
            "  [6] Add label\n"
            "  [7] Edit label\n"
            "  [8] Remove label\n"
            "  [9] Preview (test a description)\n"
            " [10] Save\n"
            " [11] Exit\n"
        ) if _RICH else (
            "\nCategory & Label Editor\n"
            "  1. List categories\n"
            "  2. Add category\n"
            "  3. Edit category\n"
            "  4. Remove category\n"
            "  5. List labels\n"
            "  6. Add label\n"
            "  7. Edit label\n"
            "  8. Remove label\n"
            "  9. Preview (test a description)\n"
            " 10. Save\n"
            " 11. Exit\n"
        )

        dispatch = {
            "1": self.list_categories,
            "2": self.add_category,
            "3": self.edit_category,
            "4": self.remove_category,
            "5": self.list_labels,
            "6": self.add_label,
            "7": self.edit_label,
            "8": self.remove_label,
            "9": self.preview,
            "10": self.save,
        }

        while True:
            dirty_indicator = (" [yellow](unsaved changes)[/yellow]" if _RICH else " (unsaved changes)") if self.dirty else ""
            _print(menu + dirty_indicator)
            choice = _input("Select an option: ").strip()

            if choice == "11":
                if self.dirty and not _confirm("You have unsaved changes. Exit anyway?"):
                    continue
                _print("Goodbye.")
                break

            handler = dispatch.get(choice)
            if handler is None:
                _print("[red]Invalid choice.[/red]" if _RICH else "Invalid choice.")
            else:
                try:
                    handler()
                except KeyboardInterrupt:
                    _print("\nOperation cancelled.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactive CLI editor for category and label rules."
    )
    parser.add_argument(
        "--categories",
        type=Path,
        default=DEFAULT_CATEGORIES_PATH,
        help=f"Path to categories JSON file (default: {DEFAULT_CATEGORIES_PATH})",
    )
    parser.add_argument(
        "--labels",
        type=Path,
        default=DEFAULT_LABELS_PATH,
        help=f"Path to labels JSON file (default: {DEFAULT_LABELS_PATH})",
    )
    args = parser.parse_args()

    editor = RulesEditor(categories_path=args.categories, labels_path=args.labels)
    try:
        editor.run()
    except KeyboardInterrupt:
        if editor.dirty:
            print("\nInterrupted. Unsaved changes were NOT saved.")
        else:
            print("\nInterrupted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
