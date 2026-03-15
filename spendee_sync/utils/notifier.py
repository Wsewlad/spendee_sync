from __future__ import annotations

import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


class Notifier:
    """Sends email and/or desktop notifications after a sync completes."""

    def notify_sync_complete(
        self,
        fetched: int,
        missing: int,
        categories: dict[str, int],
        output_path: str,
        errors: list[str] = None,
    ) -> None:
        """Send all configured notifications."""
        summary = self._build_summary_text(fetched, missing, categories)
        subject = f"Spendee Sync: {missing} new transaction(s) found"

        if os.environ.get("NOTIFY_EMAIL_TO"):
            html_body = self._build_html_body(fetched, missing, categories, output_path, errors)
            self._send_email(subject, html_body)

        if os.environ.get("NOTIFY_DESKTOP", "").lower() == "true":
            self._send_desktop("Spendee Sync", summary)

    def _build_summary_text(
        self,
        fetched: int,
        missing: int,
        categories: dict[str, int],
    ) -> str:
        """Build a short plain-text summary."""
        parts = [f"Synced {missing} new transactions out of {fetched} fetched."]
        if categories:
            cat_parts = ", ".join(f"{cat} ({count})" for cat, count in categories.items())
            parts.append(f"Categories: {cat_parts}.")
        return " ".join(parts)

    def _build_html_body(
        self,
        fetched: int,
        missing: int,
        categories: dict[str, int],
        output_path: str,
        errors: list[str] = None,
    ) -> str:
        """Build an HTML email body with a sync summary table."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        rows = ""
        for cat, count in categories.items():
            rows += f"<tr><td>{cat}</td><td>{count}</td></tr>\n"

        if not rows:
            rows = "<tr><td colspan='2'><em>No category data</em></td></tr>"

        errors_section = ""
        if errors:
            error_items = "".join(f"<li>{e}</li>" for e in errors)
            errors_section = f"""
            <h3 style="color:#c0392b;">Errors</h3>
            <ul>{error_items}</ul>
            """

        html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: Arial, sans-serif; font-size: 14px; color: #333; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 480px; }}
    th {{ background-color: #2c3e50; color: #fff; padding: 8px 12px; text-align: left; }}
    td {{ padding: 6px 12px; border-bottom: 1px solid #ddd; }}
    tr:nth-child(even) {{ background-color: #f9f9f9; }}
    .meta {{ color: #777; font-size: 12px; margin-top: 16px; }}
  </style>
</head>
<body>
  <h2>Spendee Sync Complete</h2>
  <p><strong>{missing} new transactions found</strong> out of {fetched} fetched from Monobank.</p>

  <h3>Category Breakdown</h3>
  <table>
    <thead>
      <tr><th>Category</th><th>Count</th></tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>

  <p class="meta">CSV exported to: <code>{output_path}</code></p>
  <p class="meta">Timestamp: {timestamp}</p>
  {errors_section}
</body>
</html>"""
        return html

    def _send_email(self, subject: str, html_body: str) -> None:
        """Send an HTML email via SMTP."""
        to_addr = os.environ["NOTIFY_EMAIL_TO"]
        from_addr = os.environ.get("NOTIFY_EMAIL_FROM", to_addr)
        smtp_host = os.environ.get("NOTIFY_SMTP_HOST", "localhost")
        smtp_port = int(os.environ.get("NOTIFY_SMTP_PORT", "587"))
        smtp_user = os.environ.get("NOTIFY_SMTP_USER", "")
        smtp_password = os.environ.get("NOTIFY_SMTP_PASSWORD", "")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            if smtp_user:
                server.login(smtp_user, smtp_password)
            server.sendmail(from_addr, [to_addr], msg.as_string())

    def _send_desktop(self, title: str, message: str) -> None:
        """Show a native OS desktop notification via plyer."""
        try:
            from plyer import notification as plyer_notification
            plyer_notification.notify(
                title=title,
                message=message,
                app_name="Spendee Sync",
                timeout=10,
            )
        except ImportError:
            pass
