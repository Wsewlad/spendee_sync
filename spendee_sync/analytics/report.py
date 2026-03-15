from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from spendee_sync.models.transaction import Transaction, TransactionType


_COLORS = [
    "#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3",
    "#937860", "#DA8BC3", "#8C8C8C", "#CCB974", "#64B5CD",
    "#E377C2", "#7F7F7F", "#BCBD22", "#17BECF", "#AEC7E8",
    "#FFBB78", "#98DF8A", "#FF9896", "#C5B0D5", "#C49C94",
]


def _transactions_to_df(transactions: list[Transaction]) -> pd.DataFrame:
    rows = []
    for tx in transactions:
        labels = tx.labels or []
        rows.append({
            "date": tx.date,
            "month": tx.date.strftime("%Y-%m"),
            "amount": float(tx.second_amount),
            "category": tx.category or "Other",
            "labels": labels,
            "description": (tx.description or "").strip(),
            "type": tx.type.value if tx.type else "Expense",
            "source": tx.source or "",
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["month"] = pd.Categorical(df["month"], categories=sorted(df["month"].unique()), ordered=True)
    return df


def _fig_monthly_summary(df: pd.DataFrame) -> go.Figure:
    """Grouped bar: income vs expenses per month."""
    months = sorted(df["month"].unique())
    income = []
    expense = []
    for m in months:
        mdf = df[df["month"] == m]
        income.append(mdf[mdf["type"] == "Income"]["amount"].sum())
        expense.append(mdf[mdf["type"] == "Expense"]["amount"].sum())

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Income", x=months, y=income, marker_color="#55A868"))
    fig.add_trace(go.Bar(name="Expenses", x=months, y=expense, marker_color="#C44E52"))
    fig.update_layout(
        title="Monthly Income vs Expenses",
        barmode="group",
        xaxis_title="Month",
        yaxis_title="Amount",
        legend=dict(orientation="h", y=1.1),
        hovermode="x unified",
    )
    return fig


def _fig_monthly_by_category(df: pd.DataFrame) -> go.Figure:
    """Stacked bar: expenses broken down by category per month."""
    expense_df = df[df["type"] == "Expense"]
    if expense_df.empty:
        return go.Figure()

    pivot = (
        expense_df.groupby(["month", "category"])["amount"]
        .sum()
        .unstack(fill_value=0)
    )
    months = list(pivot.index)
    categories = list(pivot.columns)

    fig = go.Figure()
    for i, cat in enumerate(categories):
        fig.add_trace(go.Bar(
            name=cat,
            x=months,
            y=pivot[cat].tolist(),
            marker_color=_COLORS[i % len(_COLORS)],
        ))
    fig.update_layout(
        title="Monthly Expenses by Category",
        barmode="stack",
        xaxis_title="Month",
        yaxis_title="Amount",
        legend=dict(orientation="h", y=-0.2, x=0),
        hovermode="x unified",
    )
    return fig


def _fig_category_donut(df: pd.DataFrame) -> go.Figure:
    """Donut chart: overall expense share by category."""
    expense_df = df[df["type"] == "Expense"]
    if expense_df.empty:
        return go.Figure()

    totals = expense_df.groupby("category")["amount"].sum().sort_values(ascending=False)
    fig = go.Figure(go.Pie(
        labels=totals.index.tolist(),
        values=totals.values.tolist(),
        hole=0.4,
        marker_colors=_COLORS[:len(totals)],
        textinfo="label+percent",
    ))
    fig.update_layout(title="Overall Expense Breakdown by Category")
    return fig


def _fig_top_descriptions(df: pd.DataFrame, top_n: int = 20) -> go.Figure:
    """Horizontal bar: top N merchants/descriptions by total spend."""
    expense_df = df[df["type"] == "Expense"]
    if expense_df.empty:
        return go.Figure()

    totals = (
        expense_df.groupby("description")["amount"]
        .sum()
        .sort_values(ascending=False)
        .head(top_n)
        .sort_values(ascending=True)  # flip so largest is at top of chart
    )
    fig = go.Figure(go.Bar(
        x=totals.values.tolist(),
        y=totals.index.tolist(),
        orientation="h",
        marker_color="#4C72B0",
    ))
    fig.update_layout(
        title=f"Top {top_n} Spending Descriptions",
        xaxis_title="Total Amount",
        yaxis_title="",
        height=max(400, top_n * 22),
        margin=dict(l=200),
    )
    return fig


def _fig_labels_breakdown(df: pd.DataFrame) -> go.Figure:
    """Horizontal bar: expense totals per label."""
    expense_df = df[df["type"] == "Expense"].copy()
    if expense_df.empty:
        return go.Figure()

    # Explode label lists
    exploded = expense_df.explode("labels")
    exploded = exploded[exploded["labels"].notna() & (exploded["labels"] != "")]
    if exploded.empty:
        return go.Figure()

    totals = (
        exploded.groupby("labels")["amount"]
        .sum()
        .sort_values(ascending=True)
    )
    fig = go.Figure(go.Bar(
        x=totals.values.tolist(),
        y=totals.index.tolist(),
        orientation="h",
        marker_color="#DD8452",
    ))
    fig.update_layout(
        title="Expenses by Label/Tag",
        xaxis_title="Total Amount",
        yaxis_title="",
        height=max(300, len(totals) * 26),
    )
    return fig


def _fig_category_trend(df: pd.DataFrame) -> go.Figure:
    """Line chart: expense per category over months."""
    expense_df = df[df["type"] == "Expense"]
    if expense_df.empty:
        return go.Figure()

    pivot = (
        expense_df.groupby(["month", "category"])["amount"]
        .sum()
        .unstack(fill_value=0)
    )
    months = list(pivot.index)
    categories = list(pivot.columns)

    fig = go.Figure()
    for i, cat in enumerate(categories):
        fig.add_trace(go.Scatter(
            name=cat,
            x=months,
            y=pivot[cat].tolist(),
            mode="lines+markers",
            marker_color=_COLORS[i % len(_COLORS)],
        ))
    fig.update_layout(
        title="Category Spending Trend Over Time",
        xaxis_title="Month",
        yaxis_title="Amount",
        legend=dict(orientation="h", y=-0.2, x=0),
        hovermode="x unified",
    )
    return fig


def _fig_monthly_net(df: pd.DataFrame) -> go.Figure:
    """Bar chart: net savings (income minus expenses) per month."""
    months = sorted(df["month"].unique())
    nets = []
    for m in months:
        mdf = df[df["month"] == m]
        income = mdf[mdf["type"] == "Income"]["amount"].sum()
        expense = mdf[mdf["type"] == "Expense"]["amount"].sum()
        nets.append(income - expense)

    colors = ["#55A868" if v >= 0 else "#C44E52" for v in nets]
    fig = go.Figure(go.Bar(
        x=months,
        y=nets,
        marker_color=colors,
    ))
    fig.update_layout(
        title="Monthly Net (Income − Expenses)",
        xaxis_title="Month",
        yaxis_title="Amount",
        hovermode="x unified",
    )
    return fig


def build_report(
    transactions: list[Transaction],
    output_path: str = "spendee_sync/outputs/report.html",
    title: str = "Spending Analytics",
) -> str:
    """Build an interactive HTML analytics report from a list of transactions.

    Args:
        transactions: List of Transaction objects (from Monobank, Spendee, or Wise).
        output_path: Path to write the HTML report.
        title: Report title shown in the browser tab and heading.

    Returns:
        Absolute path of the written HTML file.
    """
    df = _transactions_to_df(transactions)

    if df.empty:
        raise ValueError("No transactions provided to build_report().")

    # Summary stats
    expense_df = df[df["type"] == "Expense"]
    income_df = df[df["type"] == "Income"]
    total_expense = expense_df["amount"].sum()
    total_income = income_df["amount"].sum()
    date_min = df["date"].min().date()
    date_max = df["date"].max().date()
    n_months = df["month"].nunique()

    summary_html = f"""
    <div class="summary">
      <div class="stat"><span class="label">Period</span><span class="value">{date_min} → {date_max}</span></div>
      <div class="stat"><span class="label">Months</span><span class="value">{n_months}</span></div>
      <div class="stat"><span class="label">Transactions</span><span class="value">{len(df):,}</span></div>
      <div class="stat income"><span class="label">Total Income</span><span class="value">{total_income:,.2f}</span></div>
      <div class="stat expense"><span class="label">Total Expenses</span><span class="value">{total_expense:,.2f}</span></div>
      <div class="stat {'net-pos' if total_income - total_expense >= 0 else 'net-neg'}">
        <span class="label">Net</span>
        <span class="value">{total_income - total_expense:+,.2f}</span>
      </div>
    </div>
    """

    # Build all charts
    figures = [
        _fig_monthly_summary(df),
        _fig_monthly_net(df),
        _fig_monthly_by_category(df),
        _fig_category_donut(df),
        _fig_category_trend(df),
        _fig_top_descriptions(df),
        _fig_labels_breakdown(df),
    ]

    # Render each figure to HTML div (no full page wrapping)
    chart_divs = []
    for fig in figures:
        if fig.data:
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(245,246,250,1)",
                font=dict(family="Inter, system-ui, sans-serif", size=13),
            )
            chart_divs.append(fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True}))

    charts_html = "\n".join(f'<div class="chart-card">{div}</div>' for div in chart_divs)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #f0f2f8;
      font-family: Inter, system-ui, sans-serif;
      color: #1a1a2e;
    }}
    header {{
      background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
      color: #fff;
      padding: 28px 40px 20px;
    }}
    header h1 {{ margin: 0 0 4px; font-size: 1.8rem; font-weight: 700; }}
    .summary {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      padding: 20px 40px;
      background: #fff;
      border-bottom: 1px solid #e0e3ef;
    }}
    .stat {{
      display: flex;
      flex-direction: column;
      background: #f7f8fc;
      border-radius: 10px;
      padding: 12px 20px;
      min-width: 140px;
    }}
    .stat .label {{ font-size: 0.75rem; color: #666; text-transform: uppercase; letter-spacing: .05em; }}
    .stat .value {{ font-size: 1.2rem; font-weight: 600; margin-top: 4px; }}
    .stat.income .value {{ color: #2a9d5c; }}
    .stat.expense .value {{ color: #c0392b; }}
    .stat.net-pos .value {{ color: #2a9d5c; }}
    .stat.net-neg .value {{ color: #c0392b; }}
    .charts {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(560px, 1fr));
      gap: 20px;
      padding: 24px 40px 40px;
    }}
    .chart-card {{
      background: #fff;
      border-radius: 14px;
      padding: 16px;
      box-shadow: 0 2px 12px rgba(0,0,0,.07);
      overflow: hidden;
    }}
    @media (max-width: 640px) {{
      .charts {{ grid-template-columns: 1fr; padding: 12px; }}
      .summary {{ padding: 12px; }}
      header {{ padding: 16px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{title}</h1>
  </header>
  {summary_html}
  <div class="charts">
    {charts_html}
  </div>
</body>
</html>
"""

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return str(out.resolve())
