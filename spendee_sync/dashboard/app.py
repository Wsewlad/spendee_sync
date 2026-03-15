"""FastAPI web dashboard application."""
from __future__ import annotations

import csv
import io
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from spendee_sync.dashboard import state

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="Spendee Sync Dashboard")


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    summary = state.get_summary()
    sync_running = state.is_sync_in_progress()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "summary": summary,
            "sync_running": sync_running,
        },
    )


# ---------------------------------------------------------------------------
# GET /transactions
# ---------------------------------------------------------------------------

@app.get("/transactions", response_class=HTMLResponse)
async def transactions_page(request: Request):
    txs = state.get_transactions()
    return templates.TemplateResponse(
        "transactions.html",
        {
            "request": request,
            "transactions": txs,
        },
    )


# ---------------------------------------------------------------------------
# POST /transactions/{tx_id}/edit
# ---------------------------------------------------------------------------

@app.post("/transactions/{tx_id}/edit")
async def edit_transaction(
    tx_id: str,
    category: Optional[str] = Form(default=None),
    labels: Optional[str] = Form(default=None),
):
    found = state.apply_override(tx_id, category, labels)
    if not found:
        return JSONResponse({"error": "Transaction not found"}, status_code=404)
    return RedirectResponse(url="/transactions", status_code=303)


# ---------------------------------------------------------------------------
# POST /sync
# ---------------------------------------------------------------------------

def _run_sync():
    """Execute the full sync in a background thread."""
    state.set_sync_in_progress(True)
    try:
        from dotenv import load_dotenv
        load_dotenv()
        from spendee_sync.task import task
        task()
        state.set_last_sync(datetime.now(timezone.utc).isoformat())
        # Reload transactions from the newly written CSV
        state.load_transactions_from_csv()
    except Exception as exc:
        # Log to stderr; don't crash the server
        import traceback
        traceback.print_exc()
    finally:
        state.set_sync_in_progress(False)


@app.post("/sync")
async def trigger_sync():
    if state.is_sync_in_progress():
        return RedirectResponse(url="/?sync=already_running", status_code=303)
    thread = threading.Thread(target=_run_sync, daemon=True)
    thread.start()
    return RedirectResponse(url="/?sync=started", status_code=303)


# ---------------------------------------------------------------------------
# GET /review
# ---------------------------------------------------------------------------

@app.get("/review", response_class=HTMLResponse)
async def review_page(request: Request):
    txs = state.get_transactions()
    return templates.TemplateResponse(
        "review.html",
        {
            "request": request,
            "transactions": txs,
        },
    )


# ---------------------------------------------------------------------------
# GET /export
# ---------------------------------------------------------------------------

SPENDEE_COLUMNS = ["Date", "Type", "Category name", "Amount", "Note", "Labels"]


@app.get("/export")
async def export_csv():
    txs = state.get_transactions()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(SPENDEE_COLUMNS)
    for tx in txs:
        writer.writerow([
            tx.get("date", ""),
            tx.get("type", ""),
            tx.get("category", ""),
            tx.get("amount", ""),
            tx.get("description", ""),
            tx.get("labels", ""),
        ])
    output.seek(0)
    filename = f"reviewed_transactions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# GET /api/status
# ---------------------------------------------------------------------------

@app.get("/api/status")
async def api_status():
    txs = state.get_transactions()
    return JSONResponse({
        "pending": len(txs),
        "last_sync": state.get_last_sync(),
        "sync_in_progress": state.is_sync_in_progress(),
    })
