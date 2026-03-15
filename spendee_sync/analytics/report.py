from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from spendee_sync.models.transaction import Transaction, TransactionType


_COLORS = [
    "#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3",
    "#937860", "#DA8BC3", "#8C8C8C", "#CCB974", "#64B5CD",
    "#E377C2", "#7F7F7F", "#BCBD22", "#17BECF", "#AEC7E8",
    "#FFBB78", "#98DF8A", "#FF9896", "#C5B0D5", "#C49C94",
]


# ── helpers ────────────────────────────────────────────────────────────────────

def _transactions_to_df(transactions: list[Transaction]) -> pd.DataFrame:
    rows = []
    for tx in transactions:
        rows.append({
            "date": tx.date,
            "month": tx.date.strftime("%Y-%m"),
            "amount": float(tx.second_amount),
            "primary_amount": float(tx.primary_amount),
            "currency": (tx.currency or "").upper(),
            "category": tx.category or "Other",
            "labels": tx.labels or [],
            "description": (tx.description or "").strip(),
            "type": tx.type.value if tx.type else "Expense",
            "source": tx.source or "",
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["month"] = pd.Categorical(df["month"], categories=sorted(df["month"].unique()), ordered=True)
    return df


def _primary_currency(df: pd.DataFrame) -> str:
    if df.empty or "currency" not in df.columns:
        return "UAH"
    counts = df[df["currency"] != ""]["currency"].value_counts()
    return counts.idxmax() if not counts.empty else "UAH"


# ── overview ───────────────────────────────────────────────────────────────────

def _fig_monthly_summary(df: pd.DataFrame) -> go.Figure | None:
    months = sorted(df["month"].unique())
    income = [df[(df["month"] == m) & (df["type"] == "Income")]["amount"].sum() for m in months]
    expense = [df[(df["month"] == m) & (df["type"] == "Expense")]["amount"].sum() for m in months]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Income", x=months, y=income, marker_color="#55A868"))
    fig.add_trace(go.Bar(name="Expenses", x=months, y=expense, marker_color="#C44E52"))
    fig.update_layout(
        title="Monthly Income vs Expenses",
        barmode="group", xaxis_title="Month", yaxis_title="Amount",
        legend=dict(orientation="h", y=1.1), hovermode="x unified",
    )
    return fig


def _fig_monthly_net(df: pd.DataFrame) -> go.Figure | None:
    months = sorted(df["month"].unique())
    nets = [
        df[(df["month"] == m) & (df["type"] == "Income")]["amount"].sum()
        - df[(df["month"] == m) & (df["type"] == "Expense")]["amount"].sum()
        for m in months
    ]
    fig = go.Figure(go.Bar(
        x=months, y=nets,
        marker_color=["#55A868" if v >= 0 else "#C44E52" for v in nets],
    ))
    fig.add_hline(y=0, line_dash="dot", line_color="gray")
    fig.update_layout(
        title="Monthly Net (Income − Expenses)",
        xaxis_title="Month", yaxis_title="Amount", hovermode="x unified",
    )
    return fig


# ── categories ─────────────────────────────────────────────────────────────────

def _fig_monthly_by_category(df: pd.DataFrame) -> go.Figure | None:
    edf = df[df["type"] == "Expense"]
    if edf.empty:
        return None
    pivot = edf.groupby(["month", "category"])["amount"].sum().unstack(fill_value=0)
    fig = go.Figure()
    for i, cat in enumerate(pivot.columns):
        fig.add_trace(go.Bar(name=cat, x=list(pivot.index), y=pivot[cat].tolist(),
                             marker_color=_COLORS[i % len(_COLORS)]))
    fig.update_layout(
        title="Monthly Expenses by Category", barmode="stack",
        xaxis_title="Month", yaxis_title="Amount",
        legend=dict(orientation="h", y=-0.25, x=0), hovermode="x unified",
    )
    return fig


def _fig_category_donut(df: pd.DataFrame) -> go.Figure | None:
    edf = df[df["type"] == "Expense"]
    if edf.empty:
        return None
    totals = edf.groupby("category")["amount"].sum().sort_values(ascending=False)
    fig = go.Figure(go.Pie(
        labels=totals.index.tolist(), values=totals.values.tolist(),
        hole=0.4, marker_colors=_COLORS[:len(totals)], textinfo="label+percent",
    ))
    fig.update_layout(title="Overall Expense Breakdown by Category")
    return fig


def _fig_category_trend(df: pd.DataFrame) -> go.Figure | None:
    edf = df[df["type"] == "Expense"]
    if edf.empty:
        return None
    pivot = edf.groupby(["month", "category"])["amount"].sum().unstack(fill_value=0)
    fig = go.Figure()
    for i, cat in enumerate(pivot.columns):
        fig.add_trace(go.Scatter(
            name=cat, x=list(pivot.index), y=pivot[cat].tolist(),
            mode="lines+markers", marker_color=_COLORS[i % len(_COLORS)],
        ))
    fig.update_layout(
        title="Category Spending Trend Over Time",
        xaxis_title="Month", yaxis_title="Amount",
        legend=dict(orientation="h", y=-0.25, x=0), hovermode="x unified",
    )
    return fig


def _fig_avg_transaction_by_category(df: pd.DataFrame) -> go.Figure | None:
    edf = df[df["type"] == "Expense"]
    if edf.empty:
        return None
    avg = edf.groupby("category")["amount"].mean().sort_values(ascending=True)
    fig = go.Figure(go.Bar(
        x=avg.values.tolist(), y=avg.index.tolist(),
        orientation="h", marker_color="#64B5CD",
    ))
    fig.update_layout(
        title="Average Transaction Size by Category",
        xaxis_title="Average Amount", margin=dict(l=140),
    )
    return fig


def _fig_category_anomalies(df: pd.DataFrame) -> go.Figure | None:
    edf = df[df["type"] == "Expense"]
    pivot = edf.groupby(["month", "category"])["amount"].sum().unstack(fill_value=0)
    if pivot.shape[0] < 2:
        return None
    std = pivot.std()
    std[std == 0] = 1  # avoid divide-by-zero for constant categories
    z = ((pivot - pivot.mean()) / std).fillna(0)
    fig = go.Figure(go.Heatmap(
        z=z.values.tolist(),
        x=z.columns.tolist(),
        y=z.index.tolist(),
        colorscale="RdYlGn_r",
        zmid=0,
        text=[[f"{v:+.1f}σ" for v in row] for row in z.values.tolist()],
        texttemplate="%{text}",
        hovertemplate="Month: %{y}<br>Category: %{x}<br>Z-score: %{z:+.2f}σ<extra></extra>",
    ))
    fig.update_layout(
        title="Category Spending Anomalies — Z-Score vs Own Average (red = unusually high)",
        xaxis_title="Category", yaxis_title="Month",
        height=max(350, pivot.shape[0] * 40 + 120),
    )
    return fig


# ── spending patterns ──────────────────────────────────────────────────────────

def _fig_day_of_week(df: pd.DataFrame) -> go.Figure | None:
    edf = df[df["type"] == "Expense"].copy()
    if edf.empty:
        return None
    edf["dow"] = edf["date"].dt.day_name()
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    totals = edf.groupby("dow")["amount"].sum().reindex(order, fill_value=0)
    colors = ["#4C72B0"] * 5 + ["#DD8452", "#DD8452"]
    fig = go.Figure(go.Bar(
        x=totals.index.tolist(), y=totals.values.tolist(), marker_color=colors,
    ))
    fig.update_layout(
        title="Total Spending by Day of Week",
        xaxis_title="", yaxis_title="Total Amount",
    )
    return fig


def _fig_time_of_day(df: pd.DataFrame) -> go.Figure | None:
    edf = df[df["type"] == "Expense"].copy()
    if edf.empty:
        return None

    def _slot(h: int) -> str:
        if 6 <= h < 12:
            return "Morning\n06:00–12:00"
        if 12 <= h < 18:
            return "Afternoon\n12:00–18:00"
        if 18 <= h < 22:
            return "Evening\n18:00–22:00"
        return "Night\n22:00–06:00"

    edf["slot"] = edf["date"].dt.hour.apply(_slot)
    order = ["Morning\n06:00–12:00", "Afternoon\n12:00–18:00",
             "Evening\n18:00–22:00", "Night\n22:00–06:00"]
    totals = edf.groupby("slot")["amount"].sum().reindex(order, fill_value=0)
    fig = go.Figure(go.Bar(
        x=totals.index.tolist(), y=totals.values.tolist(),
        marker_color=_COLORS[:4],
    ))
    fig.update_layout(
        title="Spending by Time of Day (UTC)",
        xaxis_title="", yaxis_title="Total Amount",
    )
    return fig


def _fig_weekend_vs_weekday(df: pd.DataFrame) -> go.Figure | None:
    edf = df[df["type"] == "Expense"].copy()
    if edf.empty:
        return None
    edf["is_weekend"] = edf["date"].dt.dayofweek >= 5
    months = sorted(df["month"].unique())
    wkday = edf[~edf["is_weekend"]].groupby("month")["amount"].mean()
    wkend = edf[edf["is_weekend"]].groupby("month")["amount"].mean()
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Weekday avg tx", x=months,
                         y=[wkday.get(m, 0) for m in months], marker_color="#4C72B0"))
    fig.add_trace(go.Bar(name="Weekend avg tx", x=months,
                         y=[wkend.get(m, 0) for m in months], marker_color="#DD8452"))
    fig.update_layout(
        title="Average Transaction Amount: Weekday vs Weekend",
        barmode="group", yaxis_title="Avg Amount per Transaction",
        legend=dict(orientation="h", y=1.1), hovermode="x unified",
    )
    return fig


def _fig_spending_frequency(df: pd.DataFrame) -> go.Figure | None:
    edf = df[df["type"] == "Expense"].copy()
    if edf.empty:
        return None
    edf["day"] = edf["date"].dt.date
    daily_counts = edf.groupby("day").size()
    fig = go.Figure(go.Histogram(
        x=daily_counts.values.tolist(), nbinsx=15,
        marker_color="#4C72B0",
    ))
    fig.update_layout(
        title="How Many Transactions Do You Make Per Day?",
        xaxis_title="Number of Transactions in a Day",
        yaxis_title="Number of Days",
    )
    return fig


# ── merchants ──────────────────────────────────────────────────────────────────

def _fig_top_descriptions(df: pd.DataFrame, top_n: int = 20) -> go.Figure | None:
    edf = df[df["type"] == "Expense"]
    if edf.empty:
        return None
    totals = edf.groupby("description")["amount"].sum().sort_values(ascending=False).head(top_n).sort_values()
    fig = go.Figure(go.Bar(
        x=totals.values.tolist(), y=totals.index.tolist(),
        orientation="h", marker_color="#4C72B0",
    ))
    fig.update_layout(
        title=f"Top {top_n} Merchants by Total Spend",
        xaxis_title="Total Amount", height=max(400, top_n * 22), margin=dict(l=200),
    )
    return fig


def _fig_top_by_count(df: pd.DataFrame, top_n: int = 20) -> go.Figure | None:
    edf = df[df["type"] == "Expense"]
    if edf.empty:
        return None
    counts = edf.groupby("description").size().sort_values(ascending=False).head(top_n).sort_values()
    fig = go.Figure(go.Bar(
        x=counts.values.tolist(), y=counts.index.tolist(),
        orientation="h", marker_color="#8172B3",
    ))
    fig.update_layout(
        title=f"Top {top_n} Most Frequent Merchants (by Visit Count)",
        xaxis_title="Number of Transactions", height=max(400, top_n * 22), margin=dict(l=200),
    )
    return fig


def _fig_recurring_expenses(df: pd.DataFrame, min_months: int = 3) -> go.Figure | None:
    edf = df[df["type"] == "Expense"]
    if edf.empty:
        return None
    merchant_months = edf.groupby("description")["month"].nunique()
    recurring = merchant_months[merchant_months >= min_months].sort_values(ascending=True)
    if recurring.empty:
        return None
    avg_amount = edf[edf["description"].isin(recurring.index)].groupby("description")["amount"].mean()
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Months active",
        x=recurring.values.tolist(), y=recurring.index.tolist(),
        orientation="h", marker_color="#4C72B0",
        xaxis="x",
        text=[f"{recurring[d]}mo  avg {avg_amount.get(d, 0):,.0f}" for d in recurring.index],
        textposition="inside",
    ))
    fig.update_layout(
        title=f"Recurring Expenses (present in ≥ {min_months} months)",
        xaxis_title="Number of Active Months",
        height=max(300, len(recurring) * 28 + 80), margin=dict(l=200),
    )
    return fig


def _fig_new_vs_returning(df: pd.DataFrame) -> go.Figure | None:
    edf = df[df["type"] == "Expense"].copy()
    if edf.empty:
        return None
    first_seen = edf.groupby("description")["month"].min()
    edf["first_month"] = edf["description"].map(first_seen)
    edf["is_new"] = edf["month"] == edf["first_month"]
    months = sorted(df["month"].unique())
    new_c = edf[edf["is_new"]].groupby("month")["description"].nunique()
    ret_c = edf[~edf["is_new"]].groupby("month")["description"].nunique()
    fig = go.Figure()
    fig.add_trace(go.Bar(name="New merchants", x=months,
                         y=[new_c.get(m, 0) for m in months], marker_color="#55A868"))
    fig.add_trace(go.Bar(name="Returning merchants", x=months,
                         y=[ret_c.get(m, 0) for m in months], marker_color="#4C72B0"))
    fig.update_layout(
        title="New vs Returning Merchants per Month",
        barmode="stack", yaxis_title="Unique Merchants",
        legend=dict(orientation="h", y=1.1), hovermode="x unified",
    )
    return fig


def _fig_largest_transactions(df: pd.DataFrame, top_n: int = 20) -> go.Figure | None:
    edf = df[df["type"] == "Expense"].nlargest(top_n, "amount")
    if edf.empty:
        return None
    fig = go.Figure(go.Table(
        header=dict(
            values=["<b>Date</b>", "<b>Description</b>", "<b>Category</b>",
                    "<b>Amount</b>", "<b>Labels</b>"],
            fill_color="#1a1a2e", font=dict(color="white", size=13), align="left",
            height=36,
        ),
        cells=dict(
            values=[
                edf["date"].dt.strftime("%Y-%m-%d").tolist(),
                edf["description"].tolist(),
                edf["category"].tolist(),
                [f"{a:,.2f}" for a in edf["amount"].tolist()],
                [", ".join(l) if isinstance(l, list) else "" for l in edf["labels"].tolist()],
            ],
            fill_color=[["#f7f8fc" if i % 2 == 0 else "#ffffff" for i in range(len(edf))]],
            align="left", font=dict(size=12), height=30,
        ),
    ))
    fig.update_layout(
        title=f"Top {top_n} Largest Individual Transactions",
        height=max(400, top_n * 32 + 120),
    )
    return fig


# ── income & savings ───────────────────────────────────────────────────────────

def _fig_savings_rate(df: pd.DataFrame) -> go.Figure | None:
    months = sorted(df["month"].unique())
    rates, net_vals = [], []
    for m in months:
        mdf = df[df["month"] == m]
        inc = mdf[mdf["type"] == "Income"]["amount"].sum()
        exp = mdf[mdf["type"] == "Expense"]["amount"].sum()
        rates.append((inc - exp) / inc * 100 if inc > 0 else 0)
        net_vals.append(inc - exp)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Savings Rate %", x=months, y=rates,
        marker_color=["#55A868" if r >= 0 else "#C44E52" for r in rates],
    ))
    fig.add_hline(y=0, line_dash="dot", line_color="gray")
    fig.update_layout(
        title="Monthly Savings Rate (%)",
        yaxis_title="Savings Rate (%)", hovermode="x unified",
    )
    return fig


def _fig_income_sources(df: pd.DataFrame) -> go.Figure | None:
    idf = df[df["type"] == "Income"]
    if idf.empty:
        return None
    totals = idf.groupby("description")["amount"].sum().sort_values(ascending=False)
    if len(totals) < 2:
        return None
    fig = go.Figure(go.Pie(
        labels=totals.index.tolist(), values=totals.values.tolist(),
        hole=0.4, marker_colors=_COLORS[:len(totals)], textinfo="label+percent",
    ))
    fig.update_layout(title="Income Sources Breakdown")
    return fig


def _fig_income_stability(df: pd.DataFrame) -> go.Figure | None:
    months = sorted(df["month"].unique())
    income_vals = [df[(df["month"] == m) & (df["type"] == "Income")]["amount"].sum() for m in months]
    if not any(v > 0 for v in income_vals):
        return None
    avg = sum(income_vals) / len(income_vals) if income_vals else 0
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Monthly Income", x=months, y=income_vals, marker_color="#55A868"))
    fig.add_hline(y=avg, line_dash="dash", line_color="#4C72B0",
                  annotation_text=f"Avg: {avg:,.0f}", annotation_position="top right")
    fig.update_layout(
        title="Monthly Income Stability",
        yaxis_title="Amount", hovermode="x unified",
    )
    return fig


# ── labels ─────────────────────────────────────────────────────────────────────

def _fig_labels_breakdown(df: pd.DataFrame) -> go.Figure | None:
    edf = df[df["type"] == "Expense"].copy()
    if edf.empty:
        return None
    exploded = edf.explode("labels")
    exploded = exploded[exploded["labels"].notna() & (exploded["labels"] != "")]
    if exploded.empty:
        return None
    totals = exploded.groupby("labels")["amount"].sum().sort_values(ascending=True)
    fig = go.Figure(go.Bar(
        x=totals.values.tolist(), y=totals.index.tolist(),
        orientation="h", marker_color="#DD8452",
    ))
    fig.update_layout(
        title="Expenses by Label / Tag",
        xaxis_title="Total Amount", height=max(300, len(totals) * 28 + 80),
    )
    return fig


def _fig_labels_monthly(df: pd.DataFrame) -> go.Figure | None:
    edf = df[df["type"] == "Expense"].copy()
    if edf.empty:
        return None
    exploded = edf.explode("labels")
    exploded = exploded[exploded["labels"].notna() & (exploded["labels"] != "")]
    if exploded.empty:
        return None
    pivot = exploded.groupby(["month", "labels"])["amount"].sum().unstack(fill_value=0)
    months = list(pivot.index)
    fig = go.Figure()
    for i, label in enumerate(pivot.columns):
        fig.add_trace(go.Bar(name=label, x=months, y=pivot[label].tolist(),
                             marker_color=_COLORS[i % len(_COLORS)]))
    fig.update_layout(
        title="Monthly Expenses by Label / Tag",
        barmode="stack", xaxis_title="Month", yaxis_title="Amount",
        legend=dict(orientation="h", y=-0.25, x=0), hovermode="x unified",
    )
    return fig


# ── multi-currency ─────────────────────────────────────────────────────────────

def _fig_foreign_currency(df: pd.DataFrame) -> go.Figure | None:
    pcur = _primary_currency(df)
    foreign = df[(df["type"] == "Expense") & (df["currency"] != pcur) & (df["currency"] != "")]
    if foreign.empty:
        return None
    # Show original (primary) amounts grouped by currency
    totals = foreign.groupby("currency")["primary_amount"].sum().sort_values(ascending=False)
    fig = go.Figure(go.Pie(
        labels=totals.index.tolist(), values=totals.values.tolist(),
        hole=0.4, marker_colors=_COLORS[:len(totals)], textinfo="label+value+percent",
    ))
    fig.update_layout(title=f"Foreign Currency Spend — original amounts (non-{pcur})")
    return fig


def _fig_travel_detection(df: pd.DataFrame) -> go.Figure | None:
    pcur = _primary_currency(df)
    foreign = df[(df["type"] == "Expense") & (df["currency"] != pcur) & (df["currency"] != "")]
    if foreign.empty:
        return None
    months = sorted(df["month"].unique())
    currencies = foreign["currency"].unique()
    fig = go.Figure()
    for i, cur in enumerate(currencies):
        cur_df = foreign[foreign["currency"] == cur]
        monthly = cur_df.groupby("month")["amount"].sum()
        fig.add_trace(go.Bar(
            name=cur, x=months,
            y=[monthly.get(m, 0) for m in months],
            marker_color=_COLORS[i % len(_COLORS)],
        ))
    fig.update_layout(
        title=f"Foreign Currency Activity by Month — local-currency equivalent (non-{pcur})",
        barmode="stack", yaxis_title=f"Amount ({pcur} equiv.)",
        legend=dict(orientation="h", y=1.1), hovermode="x unified",
    )
    return fig


# ── trends ─────────────────────────────────────────────────────────────────────

def _fig_mom_change(df: pd.DataFrame) -> go.Figure | None:
    edf = df[df["type"] == "Expense"]
    pivot = edf.groupby(["month", "category"])["amount"].sum().unstack(fill_value=0)
    if pivot.shape[0] < 2:
        return None
    pct = (pivot.pct_change() * 100).iloc[1:].fillna(0).clip(-200, 200)
    fig = go.Figure(go.Heatmap(
        z=pct.values.tolist(),
        x=pct.columns.tolist(),
        y=pct.index.tolist(),
        colorscale="RdYlGn_r",
        zmid=0,
        text=[[f"{v:+.0f}%" for v in row] for row in pct.values.tolist()],
        texttemplate="%{text}",
        hovertemplate="Month: %{y}<br>Category: %{x}<br>Change: %{z:+.1f}%<extra></extra>",
    ))
    fig.update_layout(
        title="Month-over-Month Spending Change (%) by Category",
        xaxis_title="Category", yaxis_title="Month",
        height=max(350, pct.shape[0] * 40 + 120),
    )
    return fig


def _fig_rolling_average(df: pd.DataFrame) -> go.Figure | None:
    edf = df[df["type"] == "Expense"]
    monthly = edf.groupby("month")["amount"].sum()
    months = sorted(monthly.index)
    if len(months) < 2:
        return None
    values = [float(monthly[m]) for m in months]
    rolling = pd.Series(values, index=months).rolling(3, min_periods=1).mean()
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Monthly Expenses", x=months, y=values,
                         marker_color="#C44E52", opacity=0.55))
    fig.add_trace(go.Scatter(name="3-Month Rolling Avg", x=months,
                             y=rolling.values.tolist(),
                             mode="lines+markers",
                             line=dict(color="#1a1a2e", width=2.5)))
    fig.update_layout(
        title="Monthly Expenses with 3-Month Rolling Average",
        yaxis_title="Amount",
        legend=dict(orientation="h", y=1.1), hovermode="x unified",
    )
    return fig


def _fig_cumulative_within_month(df: pd.DataFrame) -> go.Figure | None:
    edf = df[df["type"] == "Expense"].copy()
    if edf.empty:
        return None
    edf["dom"] = edf["date"].dt.day
    months = sorted(edf["month"].unique())
    fig = go.Figure()
    for i, m in enumerate(months):
        mdf = edf[edf["month"] == m].groupby("dom")["amount"].sum()
        last_day = int(mdf.index.max()) if not mdf.empty else 1
        full = pd.Series(0.0, index=range(1, last_day + 1))
        full.update(mdf)
        cumsum = full.cumsum()
        fig.add_trace(go.Scatter(
            name=m, x=list(range(1, last_day + 1)), y=cumsum.values.tolist(),
            mode="lines", line=dict(color=_COLORS[i % len(_COLORS)]),
        ))
    fig.update_layout(
        title="Cumulative Spending Curve Within Each Month",
        xaxis_title="Day of Month", yaxis_title="Cumulative Amount",
        legend=dict(orientation="h", y=-0.2, x=0), hovermode="x unified",
    )
    return fig


# ── report builder ─────────────────────────────────────────────────────────────

def build_report(
    transactions: list[Transaction],
    output_path: str = "spendee_sync/outputs/report.html",
    title: str = "Spending Analytics",
) -> str:
    df = _transactions_to_df(transactions)
    if df.empty:
        raise ValueError("No transactions provided to build_report().")

    # Summary stats
    edf = df[df["type"] == "Expense"]
    idf = df[df["type"] == "Income"]
    total_expense = edf["amount"].sum()
    total_income = idf["amount"].sum()
    date_min = df["date"].min().date()
    date_max = df["date"].max().date()
    n_months = df["month"].nunique()

    summary_html = f"""
    <div class="summary">
      <div class="stat"><span class="label">Period</span><span class="value">{date_min} → {date_max}</span></div>
      <div class="stat"><span class="label">Months</span><span class="value">{n_months}</span></div>
      <div class="stat"><span class="label">Transactions</span><span class="value">{len(df):,}</span></div>
      <div class="stat income"><span class="label">Total Income</span><span class="value">{total_income:,.0f}</span></div>
      <div class="stat expense"><span class="label">Total Expenses</span><span class="value">{total_expense:,.0f}</span></div>
      <div class="stat {'net-pos' if total_income >= total_expense else 'net-neg'}">
        <span class="label">Net</span>
        <span class="value">{total_income - total_expense:+,.0f}</span>
      </div>
    </div>"""

    # (section_id, title, emoji, [(fig, full_width), ...])
    sections = [
        ("overview", "Overview", "📊", [
            (_fig_monthly_summary(df), False),
            (_fig_monthly_net(df), False),
        ]),
        ("categories", "Categories", "🏷️", [
            (_fig_monthly_by_category(df), False),
            (_fig_category_donut(df), False),
            (_fig_category_trend(df), False),
            (_fig_avg_transaction_by_category(df), False),
            (_fig_category_anomalies(df), True),
        ]),
        ("patterns", "Spending Patterns", "📅", [
            (_fig_day_of_week(df), False),
            (_fig_time_of_day(df), False),
            (_fig_weekend_vs_weekday(df), False),
            (_fig_spending_frequency(df), False),
        ]),
        ("merchants", "Merchants & Transactions", "🏪", [
            (_fig_top_descriptions(df), False),
            (_fig_top_by_count(df), False),
            (_fig_recurring_expenses(df), False),
            (_fig_new_vs_returning(df), False),
            (_fig_largest_transactions(df), True),
        ]),
        ("income", "Income & Savings", "💰", [
            (_fig_savings_rate(df), False),
            (_fig_income_stability(df), False),
            (_fig_income_sources(df), False),
        ]),
        ("labels", "Labels & Tags", "🔖", [
            (_fig_labels_breakdown(df), False),
            (_fig_labels_monthly(df), False),
        ]),
        ("currency", "Multi-Currency", "💱", [
            (_fig_foreign_currency(df), False),
            (_fig_travel_detection(df), False),
        ]),
        ("trends", "Trends", "📈", [
            (_fig_rolling_average(df), False),
            (_fig_cumulative_within_month(df), False),
            (_fig_mom_change(df), True),
        ]),
    ]

    def _render_fig(fig: go.Figure | None) -> str | None:
        if fig is None or not fig.data:
            return None
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(245,246,250,1)",
            font=dict(family="Inter, system-ui, sans-serif", size=13),
            margin=dict(t=50, b=10, l=10, r=10),
        )
        return fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})

    # Build nav + section HTML
    nav_items = []
    section_html_parts = []

    for sec_id, sec_title, emoji, charts in sections:
        rendered = [(html, fw) for fig, fw in charts
                    if (html := _render_fig(fig)) is not None]
        if not rendered:
            continue

        nav_items.append(f'<a href="#{sec_id}">{emoji} {sec_title}</a>')

        cards = ""
        for html, full_width in rendered:
            cls = "chart-card full-width" if full_width else "chart-card"
            cards += f'<div class="{cls}">{html}</div>\n'

        section_html_parts.append(f"""
        <section id="{sec_id}">
          <h2>{emoji} {sec_title}</h2>
          <div class="chart-grid">{cards}</div>
        </section>""")

    nav_html = "\n".join(nav_items)
    sections_html = "\n".join(section_html_parts)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{title}</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: #f0f2f8; font-family: Inter, system-ui, sans-serif; color: #1a1a2e; }}

    header {{
      background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
      color: #fff; padding: 24px 40px 16px;
    }}
    header h1 {{ font-size: 1.75rem; font-weight: 700; }}

    .summary {{
      display: flex; flex-wrap: wrap; gap: 10px;
      padding: 16px 40px; background: #fff; border-bottom: 1px solid #e0e3ef;
    }}
    .stat {{
      display: flex; flex-direction: column;
      background: #f7f8fc; border-radius: 10px; padding: 10px 18px; min-width: 130px;
    }}
    .stat .label {{ font-size: .72rem; color: #777; text-transform: uppercase; letter-spacing: .05em; }}
    .stat .value {{ font-size: 1.15rem; font-weight: 600; margin-top: 3px; }}
    .stat.income .value  {{ color: #2a9d5c; }}
    .stat.expense .value {{ color: #c0392b; }}
    .stat.net-pos .value {{ color: #2a9d5c; }}
    .stat.net-neg .value {{ color: #c0392b; }}

    nav {{
      position: sticky; top: 0; z-index: 100;
      background: #1a1a2e; display: flex; flex-wrap: wrap; gap: 2px; padding: 0 32px;
      box-shadow: 0 2px 8px rgba(0,0,0,.25);
    }}
    nav a {{
      color: #aab4c8; text-decoration: none; font-size: .82rem; font-weight: 500;
      padding: 10px 14px; white-space: nowrap; transition: color .15s, border-bottom .15s;
      border-bottom: 2px solid transparent;
    }}
    nav a:hover {{ color: #fff; border-bottom-color: #4C72B0; }}

    main {{ padding: 28px 36px 56px; }}

    section {{ margin-bottom: 40px; scroll-margin-top: 48px; }}
    section h2 {{ font-size: 1.2rem; font-weight: 700; margin-bottom: 16px; color: #1a1a2e; }}

    .chart-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 18px;
    }}
    .chart-card {{
      background: #fff; border-radius: 14px; padding: 14px;
      box-shadow: 0 2px 12px rgba(0,0,0,.07); overflow: hidden;
    }}
    .chart-card.full-width {{ grid-column: 1 / -1; }}

    @media (max-width: 900px) {{
      .chart-grid {{ grid-template-columns: 1fr; }}
      .chart-card.full-width {{ grid-column: 1; }}
      main {{ padding: 16px; }}
      .summary {{ padding: 12px 16px; }}
      header {{ padding: 16px; }}
      nav {{ padding: 0 8px; }}
    }}
  </style>
</head>
<body>
  <header><h1>{title}</h1></header>
  {summary_html}
  <nav>{nav_html}</nav>
  <main>{sections_html}</main>
</body>
</html>
"""

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return str(out.resolve())
