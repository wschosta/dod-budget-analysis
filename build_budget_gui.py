"""
DoD Budget Database Builder - Tkinter GUI

A graphical progress window for building / updating the budget database.
Runs the ingestion pipeline in a background thread and shows real-time
progress with a progress bar, file-level status, and running totals.

Usage:
    python build_budget_gui.py
"""

import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

from build_budget_db import build_database, DEFAULT_DB_PATH, DOCS_DIR


# ── Colour palette ────────────────────────────────────────────────────────────

BG         = "#1e1e2e"
BG_CARD    = "#282840"
FG         = "#cdd6f4"
FG_DIM     = "#6c7086"
ACCENT     = "#89b4fa"
GREEN      = "#a6e3a1"
YELLOW     = "#f9e2af"
RED        = "#f38ba8"
BORDER     = "#45475a"


class BuildProgressWindow:
    """Tkinter window that shows database build progress."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("DoD Budget Database Builder")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.minsize(640, 480)

        # Centre on screen
        w, h = 720, 540
        sx = self.root.winfo_screenwidth()
        sy = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sx-w)//2}+{(sy-h)//2}")

        # Thread-safe message queue: (phase, current, total, detail)
        self.msg_queue: queue.Queue = queue.Queue()
        self.build_thread: threading.Thread | None = None
        self.start_time: float | None = None
        self.running = False

        self._build_ui()
        self._poll_queue()

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self):
        # Style
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Card.TFrame", background=BG_CARD)
        style.configure("Dark.TLabel", background=BG, foreground=FG,
                         font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=BG, foreground=ACCENT,
                         font=("Segoe UI", 16, "bold"))
        style.configure("Phase.TLabel", background=BG_CARD, foreground=YELLOW,
                         font=("Segoe UI", 11, "bold"))
        style.configure("Detail.TLabel", background=BG_CARD, foreground=FG,
                         font=("Segoe UI", 9))
        style.configure("Stat.TLabel", background=BG_CARD, foreground=FG,
                         font=("Consolas", 10))
        style.configure("Green.Horizontal.TProgressbar",
                         troughcolor=BORDER, background=GREEN)
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))

        # ── Header ──
        ttk.Label(self.root, text="DoD Budget Database Builder",
                  style="Title.TLabel").pack(pady=(16, 4))
        ttk.Label(self.root, text="Ingest Excel & PDF budget documents into a searchable SQLite database",
                  style="Dark.TLabel").pack(pady=(0, 12))

        # ── Path selectors ──
        paths_frame = tk.Frame(self.root, bg=BG)
        paths_frame.pack(fill="x", padx=20, pady=(0, 8))

        # Docs directory
        tk.Label(paths_frame, text="Documents:", bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w")
        self.docs_var = tk.StringVar(value=str(DOCS_DIR))
        docs_entry = tk.Entry(paths_frame, textvariable=self.docs_var, width=55,
                              bg=BG_CARD, fg=FG, insertbackground=FG,
                              relief="flat", font=("Consolas", 9))
        docs_entry.grid(row=0, column=1, padx=(6, 4), pady=2, sticky="ew")
        tk.Button(paths_frame, text="...", width=3, bg=BG_CARD, fg=FG,
                  relief="flat", command=self._browse_docs).grid(row=0, column=2)

        # DB path
        tk.Label(paths_frame, text="Database:", bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w")
        self.db_var = tk.StringVar(value=str(DEFAULT_DB_PATH))
        db_entry = tk.Entry(paths_frame, textvariable=self.db_var, width=55,
                            bg=BG_CARD, fg=FG, insertbackground=FG,
                            relief="flat", font=("Consolas", 9))
        db_entry.grid(row=1, column=1, padx=(6, 4), pady=2, sticky="ew")
        tk.Button(paths_frame, text="...", width=3, bg=BG_CARD, fg=FG,
                  relief="flat", command=self._browse_db).grid(row=1, column=2)

        paths_frame.columnconfigure(1, weight=1)

        # ── Options row ──
        opt_frame = tk.Frame(self.root, bg=BG)
        opt_frame.pack(fill="x", padx=20, pady=(0, 10))

        self.rebuild_var = tk.BooleanVar(value=False)
        tk.Checkbutton(opt_frame, text="Full rebuild (delete existing DB)",
                       variable=self.rebuild_var, bg=BG, fg=FG,
                       selectcolor=BG_CARD, activebackground=BG,
                       activeforeground=FG, font=("Segoe UI", 9)
                       ).pack(side="left")

        # ── Progress card ──
        card = tk.Frame(self.root, bg=BG_CARD, highlightbackground=BORDER,
                        highlightthickness=1)
        card.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # Phase label
        self.phase_label = ttk.Label(card, text="Ready", style="Phase.TLabel")
        self.phase_label.pack(anchor="w", padx=14, pady=(12, 2))

        # Detail label (current file)
        self.detail_label = ttk.Label(card, text="Press 'Build Database' to start",
                                      style="Detail.TLabel", wraplength=650)
        self.detail_label.pack(anchor="w", padx=14, pady=(0, 8))

        # Progress bar
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            card, variable=self.progress_var, maximum=100,
            style="Green.Horizontal.TProgressbar", length=400)
        self.progress_bar.pack(fill="x", padx=14, pady=(0, 4))

        # Percent + ETA row
        pct_frame = tk.Frame(card, bg=BG_CARD)
        pct_frame.pack(fill="x", padx=14)
        self.pct_label = ttk.Label(pct_frame, text="0%", style="Stat.TLabel")
        self.pct_label.pack(side="left")
        self.eta_label = ttk.Label(pct_frame, text="", style="Stat.TLabel")
        self.eta_label.pack(side="right")

        # Stats text
        self.stats_text = tk.Text(card, height=8, bg=BG_CARD, fg=FG,
                                  font=("Consolas", 9), relief="flat",
                                  insertbackground=FG, wrap="word",
                                  state="disabled", borderwidth=0)
        self.stats_text.pack(fill="both", expand=True, padx=14, pady=(8, 12))
        self.stats_text.tag_configure("phase", foreground=YELLOW)
        self.stats_text.tag_configure("ok", foreground=GREEN)
        self.stats_text.tag_configure("err", foreground=RED)
        self.stats_text.tag_configure("dim", foreground=FG_DIM)

        # ── Button row ──
        btn_frame = tk.Frame(self.root, bg=BG)
        btn_frame.pack(fill="x", padx=20, pady=(0, 16))

        self.build_btn = tk.Button(
            btn_frame, text="Build Database", width=18,
            bg=ACCENT, fg="#1e1e2e", activebackground=GREEN,
            font=("Segoe UI", 11, "bold"), relief="flat",
            command=self._start_build)
        self.build_btn.pack(side="left", padx=(0, 10))

        self.close_btn = tk.Button(
            btn_frame, text="Close", width=10,
            bg=BG_CARD, fg=FG, activebackground=BORDER,
            font=("Segoe UI", 10), relief="flat",
            command=self._on_close)
        self.close_btn.pack(side="right")

    # ── Path browsing ─────────────────────────────────────────────────────

    def _browse_docs(self):
        d = filedialog.askdirectory(title="Select Documents Directory",
                                    initialdir=self.docs_var.get())
        if d:
            self.docs_var.set(d)

    def _browse_db(self):
        f = filedialog.asksaveasfilename(
            title="Database File", defaultextension=".sqlite",
            filetypes=[("SQLite", "*.sqlite"), ("All", "*.*")],
            initialfile=self.db_var.get())
        if f:
            self.db_var.set(f)

    # ── Build control ─────────────────────────────────────────────────────

    # TODO: Add a cancellation mechanism — set a threading.Event that the progress
    # callback checks, and convert the "Build Database" button to a "Cancel" button
    # while a build is running. Currently, closing the window during a build silently
    # continues the thread in the background until the process exits.
    def _start_build(self):
        docs = Path(self.docs_var.get())
        db = Path(self.db_var.get())

        if not docs.exists():
            messagebox.showerror("Error", f"Documents directory not found:\n{docs}")
            return

        self.running = True
        self.start_time = time.time()
        self.build_btn.configure(state="disabled", text="Building...", bg=FG_DIM)
        self._clear_log()
        self._log("Build started...\n", "phase")

        rebuild = self.rebuild_var.get()
        self.build_thread = threading.Thread(
            target=self._run_build, args=(docs, db, rebuild), daemon=True)
        self.build_thread.start()

    def _run_build(self, docs: Path, db: Path, rebuild: bool):
        """Runs in the background thread."""
        try:
            build_database(docs, db, rebuild=rebuild,
                           progress_callback=self._on_progress)
        except Exception as e:
            self.msg_queue.put(("error", 0, 0, str(e)))

    def _on_progress(self, phase: str, current: int, total: int, detail: str):
        """Called from the build thread — posts to the queue."""
        self.msg_queue.put((phase, current, total, detail))

    # ── Queue polling (runs on the main / UI thread) ──────────────────────

    def _poll_queue(self):
        try:
            while True:
                phase, current, total, detail = self.msg_queue.get_nowait()
                self._handle_progress(phase, current, total, detail)
        except queue.Empty:
            pass
        self.root.after(80, self._poll_queue)

    def _handle_progress(self, phase: str, current: int, total: int,
                         detail: str):
        phase_labels = {
            "scan":  "Scanning files...",
            "excel": "Ingesting Excel files",
            "pdf":   "Ingesting PDF files",
            "index": "Creating indexes",
            "done":  "Build complete",
            "error": "Error",
        }
        self.phase_label.configure(text=phase_labels.get(phase, phase))
        self.detail_label.configure(text=detail[:120] if detail else "")

        # Update progress bar
        if total > 0:
            pct = (current / total) * 100
            self.progress_var.set(pct)
            self.pct_label.configure(text=f"{pct:.0f}%")

            # TODO: ETA estimate is based on overall elapsed/current, which skews
            # when the excel and pdf phases have very different per-file times.
            # Track phase-specific start times for more accurate ETAs.
            if self.start_time and current > 0 and phase in ("excel", "pdf"):
                elapsed = time.time() - self.start_time
                rate = elapsed / current
                remaining = rate * (total - current)
                if remaining > 60:
                    self.eta_label.configure(text=f"~{remaining/60:.1f} min remaining")
                else:
                    self.eta_label.configure(text=f"~{remaining:.0f}s remaining")
            else:
                self.eta_label.configure(text="")

        # Log detail
        if detail and "Skipped" not in detail:
            tag = "ok" if phase == "done" else ("err" if phase == "error" else None)
            self._log(f"[{phase:>5}] {detail}\n", tag)

        # Build finished
        if phase == "done":
            self.running = False
            self.progress_var.set(100)
            self.pct_label.configure(text="100%")
            self.eta_label.configure(text="")
            elapsed = time.time() - self.start_time if self.start_time else 0
            self._log(f"\nCompleted in {elapsed:.1f}s\n", "ok")
            self.build_btn.configure(state="normal", text="Build Database",
                                     bg=ACCENT)
            self.phase_label.configure(text="Build complete")

        if phase == "error":
            self.running = False
            self._log(f"\nERROR: {detail}\n", "err")
            self.build_btn.configure(state="normal", text="Build Database",
                                     bg=ACCENT)

    # ── Log text widget helpers ───────────────────────────────────────────

    def _log(self, msg: str, tag: str | None = None):
        self.stats_text.configure(state="normal")
        if tag:
            self.stats_text.insert("end", msg, tag)
        else:
            self.stats_text.insert("end", msg)
        self.stats_text.see("end")
        self.stats_text.configure(state="disabled")

    def _clear_log(self):
        self.stats_text.configure(state="normal")
        self.stats_text.delete("1.0", "end")
        self.stats_text.configure(state="disabled")

    # ── Close handling ────────────────────────────────────────────────────

    def _on_close(self):
        if self.running:
            if not messagebox.askyesno("Build in progress",
                                       "A build is in progress. Close anyway?"):
                return
        self.root.destroy()

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()


def main():
    app = BuildProgressWindow()
    app.run()


if __name__ == "__main__":
    main()
