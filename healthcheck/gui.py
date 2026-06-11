"""Simple GUI wrapper for System Health Check.

Double-click to run — shows results in a window.
Supports Chinese/English language switching.
Uses tkinter (built into Python, no extra dependencies).
"""

from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from tkinter import scrolledtext, ttk
from typing import Any

from .config import Config
from .dataclasses import HealthStatus, ModuleResult
from .i18n import get_language, set_language, t
from .main import MODULE_REGISTRY, run_checks


class HealthCheckGUI:
    """Tkinter GUI for system health check."""

    STATUS_COLORS: dict[HealthStatus, str] = {
        HealthStatus.OK: "#28a745",
        HealthStatus.WARNING: "#ffc107",
        HealthStatus.CRITICAL: "#dc3545",
        HealthStatus.ERROR: "#dc3545",
        HealthStatus.NA: "#6c757d",
    }

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(t("gui.title"))
        self.root.geometry("800x640")
        self.root.minsize(640, 420)

        # Style
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # Queue for thread-safe UI updates
        self._queue: queue.Queue[Any] = queue.Queue()

        self._build_ui()

    def _build_ui(self) -> None:
        """Build the GUI layout."""
        # Top frame: title and controls
        top_frame = ttk.Frame(self.root, padding=12)
        top_frame.pack(fill=tk.X)

        self.title_label = ttk.Label(
            top_frame,
            text=t("gui.title"),
            font=("Microsoft YaHei", 16, "bold"),
        )
        self.title_label.pack(side=tk.LEFT)

        # Language toggle button
        self.lang_btn = ttk.Button(
            top_frame,
            text=t("gui.language"),
            command=self._toggle_language,
            width=8,
        )
        self.lang_btn.pack(side=tk.RIGHT, padx=(4, 0))

        self.run_btn = ttk.Button(
            top_frame,
            text=t("gui.run_check"),
            command=self._start_check,
        )
        self.run_btn.pack(side=tk.RIGHT, padx=4)

        self.progress = ttk.Progressbar(
            top_frame,
            mode="indeterminate",
            length=120,
        )

        # Status summary frame
        self.summary_frame = ttk.Frame(self.root, padding="12 0 12 6")
        self.summary_frame.pack(fill=tk.X)

        # Main text area
        self.text = scrolledtext.ScrolledText(
            self.root,
            wrap=tk.WORD,
            font=("Consolas", 10),
            bg="#1a1a2e",
            fg="#e0e0e0",
            insertbackground="#e0e0e0",
            padx=10,
            pady=10,
        )
        self.text.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        # Configure text tags for colors
        self.text.tag_configure("pass", foreground="#28a745")
        self.text.tag_configure("warn", foreground="#ffc107")
        self.text.tag_configure("fail", foreground="#dc3545")
        self.text.tag_configure("error", foreground="#dc3545")
        self.text.tag_configure("na", foreground="#6c757d")
        self.text.tag_configure("header", font=("Microsoft YaHei", 11, "bold"))
        self.text.tag_configure("module", font=("Microsoft YaHei", 10, "bold"),
                               foreground="#00bcd4")
        self.text.tag_configure("metric", foreground="#aaa")

        # Bottom status bar
        self.status_bar = ttk.Label(
            self.root,
            text=t("gui.ready"),
            relief=tk.SUNKEN,
            anchor=tk.W,
            padding=4,
        )
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        # Schedule queue polling
        self.root.after(100, self._poll_queue)

    def _toggle_language(self) -> None:
        """Switch between Chinese and English."""
        new_lang = "en" if get_language() == "zh" else "zh"
        set_language(new_lang)
        self._refresh_ui_texts()

    def _refresh_ui_texts(self) -> None:
        """Update all UI text to current language."""
        self.root.title(t("gui.title"))
        self.title_label.config(text=t("gui.title"))
        self.run_btn.config(text=t("gui.run_check"))
        self.lang_btn.config(text=t("gui.language"))
        if self.run_btn["state"] == tk.NORMAL:
            self.status_bar.config(text=t("gui.ready"))

    def _start_check(self) -> None:
        """Start health check in a background thread."""
        self.run_btn.config(state=tk.DISABLED)
        self.lang_btn.config(state=tk.DISABLED)
        self.progress.pack(side=tk.RIGHT, padx=4)
        self.progress.start()
        self.status_bar.config(text=t("gui.running"))

        self.text.delete(1.0, tk.END)
        self._insert(t("report.system_health_check") + "\n", "header")

        # Clear summary widgets
        for w in self.summary_frame.winfo_children():
            w.destroy()

        thread = threading.Thread(target=self._run_checks, daemon=True)
        thread.start()

    def _run_checks(self) -> None:
        """Run health checks (called in background thread)."""
        try:
            results = run_checks()
            self._queue.put(("done", results))
        except Exception as e:
            self._queue.put(("error", str(e)))

    def _poll_queue(self) -> None:
        """Poll the queue for thread-safe updates."""
        try:
            while True:
                msg_type, data = self._queue.get_nowait()
                try:
                    if msg_type == "done":
                        self._show_results(data)
                    elif msg_type == "error":
                        self._insert(f"\n[ERROR] {data}\n", "error")
                except Exception as e:
                    self._insert(f"\n[ERROR] Display error: {e}\n", "error")
                finally:
                    if msg_type in ("done", "error"):
                        self._on_complete()
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _show_results(self, results: list[ModuleResult]) -> None:
        """Display results in the text widget."""
        # Compute overall status
        worst = HealthStatus.OK
        for r in results:
            if r.status.weight > worst.weight:
                worst = r.status

        status_label = t(f"status.{worst.value}")
        overall_tag = self._status_tag(worst)
        self._insert(
            f"{t('gui.overall_status')}: {status_label}\n\n",
            overall_tag,
        )

        # Summary widgets
        counts = {s: 0 for s in HealthStatus}
        for r in results:
            counts[r.status] += 1

        summary_text = "  ".join(
            f"{t(f'status.{s.value}')}: {counts[s]}"
            for s in [HealthStatus.OK, HealthStatus.WARNING,
                       HealthStatus.CRITICAL, HealthStatus.ERROR, HealthStatus.NA]
            if counts[s] > 0
        )
        ttk.Label(
            self.summary_frame,
            text=summary_text,
            font=("Microsoft YaHei", 10),
        ).pack(side=tk.LEFT)

        # Per-module results
        for result in results:
            tag = self._status_tag(result.status)
            label = t(f"status.{result.status.value}")
            module_name = t(f"modules.{result.module}")
            self._insert(
                f"\n{'=' * 60}\n",
                tag,
            )
            self._insert(
                f"[{label}] {module_name}\n",
                "module",
            )

            for m in result.metrics:
                mtag = self._status_tag(m.status)
                mlabel = t(f"status.{m.status.value}")
                val_str = ""
                if m.value is not None:
                    val_str = f" {m.value}{m.unit}"
                    val_str = val_str.replace("\xb0C", " C")

                self._insert(
                    f"  [{mlabel:4s}] {m.name:<28s} {val_str:>12s}  ",
                    mtag,
                )
                self._insert(f"{m.message}\n", "metric")

            if result.error:
                self._insert(f"  [{t('status.ERROR')}] {result.error}\n", "error")

        self._insert(f"\n{'=' * 60}\n", overall_tag)
        self.text.see(1.0)  # Scroll to top

    def _on_complete(self) -> None:
        """Re-enable UI after check completes."""
        self.progress.stop()
        self.progress.pack_forget()
        self.run_btn.config(state=tk.NORMAL)
        self.lang_btn.config(state=tk.NORMAL)
        self.status_bar.config(text=t("gui.complete"))

    def _insert(self, text: str, tag: str | None = None) -> None:
        """Insert text with optional tag (thread-safe via queue)."""
        self.text.insert(tk.END, text, tag)

    def _status_tag(self, status: HealthStatus) -> str:
        """Map HealthStatus to text tag name."""
        return {
            HealthStatus.OK: "pass",
            HealthStatus.WARNING: "warn",
            HealthStatus.CRITICAL: "fail",
            HealthStatus.ERROR: "error",
            HealthStatus.NA: "na",
        }.get(status, "na")

    def run(self) -> None:
        """Start the GUI main loop."""
        # Auto-run on startup
        self.root.after(400, self._start_check)
        self.root.mainloop()


def main() -> None:
    """Entry point for the GUI app."""
    app = HealthCheckGUI()
    app.run()


if __name__ == "__main__":
    main()
