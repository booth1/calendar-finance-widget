from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from dataclasses import dataclass, asdict
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from pathlib import Path
import json
import csv
import calendar

# -------- Data model --------

@dataclass
class Transaction:
    date: date
    amount: float
    party: str
    category: str
    kind: str  # "income" or "expense"

    def to_json(self) -> Dict:
        d = asdict(self)
        d["date"] = self.date.isoformat()
        return d

    @staticmethod
    def from_json(data: Dict) -> "Transaction":
        return Transaction(
            date=datetime.fromisoformat(data["date"]).date(),
            amount=float(data["amount"]),
            party=str(data.get("party", "")),
            category=str(data.get("category", "")),
            kind=str(data["kind"]),
        )

class FinanceBook:
    def __init__(self, transactions: Optional[List[Transaction]] = None):
        self.transactions: List[Transaction] = transactions or []

    def add(self, tx: Transaction) -> None:
        self.transactions.append(tx)

    def all_years(self) -> List[int]:
        years = sorted({tx.date.year for tx in self.transactions})
        return years or [date.today().year]

    def for_year(self, year: int) -> List[Transaction]:
        return [tx for tx in self.transactions if tx.date.year == year]

    def for_year_and_month(self, year: int, month: Optional[int]) -> List[Transaction]:
        if month is None:
            return self.for_year(year)
        return [tx for tx in self.transactions if tx.date.year == year and tx.date.month == month]

    def monthly_totals(self, year: int) -> Dict[int, Dict[str, float]]:
        totals = {m: {"income": 0.0, "expense": 0.0, "net": 0.0} for m in range(1, 13)}
        for tx in self.for_year(year):
            if tx.kind == "income":
                totals[tx.date.month]["income"] += tx.amount
            else:
                totals[tx.date.month]["expense"] += tx.amount
        for m in totals:
            totals[m]["net"] = totals[m]["income"] - totals[m]["expense"]
        return totals

    def yearly_totals(self, year: int) -> Dict[str, float]:
        mt = self.monthly_totals(year)
        income = sum(mt[m]["income"] for m in mt)
        expense = sum(mt[m]["expense"] for m in mt)
        return {"income": income, "expense": expense, "net": income - expense}

    def category_totals(self, year: int, kind: str, month: Optional[int] = None) -> List[Tuple[str, float]]:
        buckets = defaultdict(float)
        for tx in self.for_year_and_month(year, month):
            if tx.kind == kind:
                buckets[tx.category or "(uncategorized)"] += tx.amount
        return sorted(buckets.items(), key=lambda kv: kv[1], reverse=True)

# -------- Storage --------

DATA_FILE = Path("finance_data.json")

def load_book() -> FinanceBook:
    if not DATA_FILE.exists():
        return FinanceBook([])
    try:
        raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        txs = [Transaction.from_json(item) for item in raw.get("transactions", [])]
        return FinanceBook(txs)
    except Exception:
        return FinanceBook([])

def save_book(book: FinanceBook) -> None:
    payload = {"transactions": [tx.to_json() for tx in book.transactions]}
    DATA_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")

# -------- UI --------

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

class FinanceApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Calendar Finance Widget")
        self.geometry("1000x680")
        self.minsize(900, 600)

        self.topmost_var = tk.BooleanVar(value=False)
        self.bind("<F12>", lambda e: self.toggle_topmost())

        self.book: FinanceBook = load_book()
        self.selected_year = tk.IntVar(value=self.book.all_years()[-1])
        self.selected_month = tk.StringVar(value="All months")
        self.chart_kind = tk.StringVar(value="expense")

        self._build_menu()
        self._build_layout()
        self._refresh_year_options()
        self.refresh_all()

    def _build_menu(self):
        menubar = tk.Menu(self)
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_checkbutton(label="Always on top (F12)", variable=self.topmost_var, command=self.toggle_topmost)
        menubar.add_cascade(label="View", menu=view_menu)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Export CSV…", command=self.export_csv)
        file_menu.add_separator()
        file_menu.add_command(label="Save", command=self.save)
        file_menu.add_command(label="Exit", command=self.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        self.config(menu=menubar)

    def toggle_topmost(self):
        self.attributes("-topmost", self.topmost_var.get())

    def _build_layout(self):
        ctrl = ttk.Frame(self, padding=(10, 10))
        ctrl.pack(fill="x")

        ttk.Label(ctrl, text="Year:").pack(side="left")
        self.year_cb = ttk.Combobox(ctrl, textvariable=self.selected_year, width=8, state="readonly")
        self.year_cb.pack(side="left", padx=(4, 12))
        self.year_cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_all())

        ttk.Label(ctrl, text="Month:").pack(side="left")
        self.month_cb = ttk.Combobox(
            ctrl,
            textvariable=self.selected_month,
            width=16,
            state="readonly",
            values=["All months"] + [calendar.month_name[m] for m in range(1, 13)],
        )
        self.month_cb.current(0)
        self.month_cb.pack(side="left", padx=(4, 12))
        self.month_cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_chart())

        ttk.Button(ctrl, text="Export CSV…", command=self.export_csv).pack(side="right", padx=4)
        ttk.Button(ctrl, text="Save", command=self.save).pack(side="right", padx=4)

        main = ttk.PanedWindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=10, pady=10)

        form = ttk.Frame(main, padding=10)
        main.add(form, weight=1)
        ttk.Label(form, text="Add transaction", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        self.date_var = tk.StringVar(value=date.today().isoformat())
        self.amount_var = tk.StringVar()
        self.party_var = tk.StringVar()
        self.category_var = tk.StringVar()

        ttk.Label(form, text="Date (YYYY-MM-DD):").grid(row=1, column=0, sticky="e")
        ttk.Entry(form, textvariable=self.date_var, width=18).grid(row=1, column=1, sticky="w", pady=2)

        ttk.Label(form, text="Amount:").grid(row=2, column=0, sticky="e")
        ttk.Entry(form, textvariable=self.amount_var, width=18).grid(row=2, column=1, sticky="w", pady=2)

        ttk.Label(form, text="Who/Party:").grid(row=3, column=0, sticky="e")
        ttk.Entry(form, textvariable=self.party_var, width=24).grid(row=3, column=1, sticky="w", pady=2)

        ttk.Label(form, text="Category:").grid(row=4, column=0, sticky="e")
        ttk.Entry(form, textvariable=self.category_var, width=24).grid(row=4, column=1, sticky="w", pady=2)

        btns = ttk.Frame(form)
        btns.grid(row=5, column=0, columnspan=2, pady=(8, 4))
        ttk.Button(btns, text="Add Income", command=lambda: self.add_tx("income")).pack(side="left", padx=5)
        ttk.Button(btns, text="Add Expense", command=lambda: self.add_tx("expense")).pack(side="left", padx=5)

        ttk.Separator(form).grid(row=6, column=0, columnspan=2, sticky="ew", pady=10)

        ttk.Label(form, text="Chart options", font=("Segoe UI", 10, "bold")).grid(row=7, column=0, columnspan=2, sticky="w")
        chart_opts = ttk.Frame(form)
        chart_opts.grid(row=8, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Radiobutton(chart_opts, text="Expense categories", variable=self.chart_kind, value="expense", command=self.refresh_chart).pack(side="left", padx=(0, 10))
        ttk.Radiobutton(chart_opts, text="Income categories", variable=self.chart_kind, value="income", command=self.refresh_chart).pack(side="left")

        right = ttk.Frame(main, padding=10)
        main.add(right, weight=3)

        ttk.Label(right, text="Transactions", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.tx_tree = ttk.Treeview(right, columns=("date", "kind", "amount", "party", "category"), show="headings", height=8)
        for col, w in [("date", 100), ("kind", 80), ("amount", 100), ("party", 180), ("category", 140)]:
            self.tx_tree.heading(col, text=col.capitalize())
            self.tx_tree.column(col, width=w, anchor="w")
        self.tx_tree.pack(fill="x", pady=(4, 10))
        ttk.Button(right, text="Delete selected", command=self.delete_selected).pack(anchor="e", pady=(0, 6))

        ttk.Label(right, text="Monthly totals (Jan → Dec)", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(6, 2))
        self.mt_tree = ttk.Treeview(right, columns=("month", "income", "expense", "net"), show="headings", height=6)
        for col, w in [("month", 120), ("income", 100), ("expense", 100), ("net", 100)]:
            self.mt_tree.heading(col, text=col.capitalize())
            self.mt_tree.column(col, width=w, anchor="w")
        self.mt_tree.pack(fill="x", pady=(4, 10))

        yt = ttk.Frame(right)
        yt.pack(fill="x", pady=(4, 8))
        self.year_income_var = tk.StringVar(value="0.00")
        self.year_expense_var = tk.StringVar(value="0.00")
        self.year_net_var = tk.StringVar(value="0.00")
        ttk.Label(yt, text="Yearly income:").grid(row=0, column=0, sticky="w")
        ttk.Label(yt, textvariable=self.year_income_var, foreground="#0a6").grid(row=0, column=1, sticky="w", padx=(6, 20))
        ttk.Label(yt, text="Yearly expense:").grid(row=0, column=2, sticky="w")
        ttk.Label(yt, textvariable=self.year_expense_var, foreground="#a00").grid(row=0, column=3, sticky="w", padx=(6, 20))
        ttk.Label(yt, text="Yearly net:").grid(row=0, column=4, sticky="w")
        ttk.Label(yt, textvariable=self.year_net_var, foreground="#06c").grid(row=0, column=5, sticky="w", padx=(6, 20))

        ttk.Label(right, text="Category breakdown (pie)", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(10, 2))
        self.figure = Figure(figsize=(4.8, 3.2), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=right)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def _refresh_year_options(self):
        years = self.book.all_years()
        if not years:
            years = [date.today().year]
        self.year_cb["values"] = years
        if self.selected_year.get() not in years:
            self.selected_year.set(years[-1])

    def add_tx(self, kind: str):
        try:
            dt = datetime.fromisoformat(self.date_var.get()).date()
        except ValueError:
            messagebox.showerror("Invalid date", "Please use YYYY-MM-DD.")
            return
        try:
            amount = float(self.amount_var.get())
        except ValueError:
            messagebox.showerror("Invalid amount", "Please enter a number (e.g., 1250.00).")
            return
        if amount < 0:
            messagebox.showerror("Invalid amount", "Amount must be positive.")
            return
        party = self.party_var.get().strip()
        category = self.category_var.get().strip()

        tx = Transaction(date=dt, amount=amount, party=party, category=category, kind=kind)
        self.book.add(tx)
        save_book(self.book)
        self.amount_var.set("")
        self._refresh_year_options()
        self.refresh_all()

    def delete_selected(self):
        selected = self.tx_tree.selection()
        if not selected:
            return
        if not messagebox.askyesno("Delete", "Delete selected transaction(s)?"):
            return
        year = self.selected_year.get()
        displayed = sorted(self.book.for_year(year), key=lambda t: t.date)
        indices_to_remove = sorted([int(self.tx_tree.set(i, "index")) for i in selected], reverse=True)
        for idx in indices_to_remove:
            target = displayed[idx]
            self.book.transactions.remove(target)
        save_book(self.book)
        self.refresh_all()

    def export_csv(self):
        year = self.selected_year.get()
        txs = self.book.for_year(year)
        if not txs:
            messagebox.showinfo("Export CSV", "No transactions for the selected year.")
            return
        path = filedialog.asksaveasfilename(
            title="Export CSV",
            defaultextension=".csv",
            initialfile=f"transactions_{year}.csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["date", "kind", "amount", "party", "category"])
            for tx in sorted(txs, key=lambda t: t.date):
                writer.writerow([tx.date.isoformat(), tx.kind, f"{tx.amount:.2f}", tx.party, tx.category])
        messagebox.showinfo("Export CSV", f"Exported {len(txs)} transactions to:\n{path}")

    def refresh_all(self):
        self.refresh_transactions()
        self.refresh_monthly_totals()
        self.refresh_yearly_totals()
        self.refresh_chart()

    def refresh_transactions(self):
        for i in self.tx_tree.get_children():
            self.tx_tree.delete(i)
        if "index" not in self.tx_tree["columns"]:
            cols = list(self.tx_tree["columns"]) + ["index"]
            self.tx_tree["columns"] = tuple(cols)
        year = self.selected_year.get()
        txs = sorted(self.book.for_year(year), key=lambda t: t.date)
        for idx, tx in enumerate(txs):
            self.tx_tree.insert(
                "",
                "end",
                values=(tx.date.isoformat(), tx.kind, f"{tx.amount:.2f}", tx.party, tx.category, idx),
            )

    def refresh_monthly_totals(self):
        for i in self.mt_tree.get_children():
            self.mt_tree.delete(i)
        mt = self.book.monthly_totals(self.selected_year.get())
        for m in range(1, 13):
            vals = mt[m]
            self.mt_tree.insert(
                "",
                "end",
                values=(calendar.month_name[m], f"{vals['income']:.2f}", f"{vals['expense']:.2f}", f"{vals['net']:.2f}"),
            )

    def refresh_yearly_totals(self):
        yt = self.book.yearly_totals(self.selected_year.get())
        self.year_income_var.set(f"{yt['income']:.2f}")
        self.year_expense_var.set(f"{yt['expense']:.2f}")
        self.year_net_var.set(f"{yt['net']:.2f}")

    def refresh_chart(self):
        self.ax.clear()
        year = self.selected_year.get()
        month_name = self.selected_month.get()
        month = None if month_name == "All months" else list(calendar.month_name).index(month_name)
        kind = self.chart_kind.get()

        data = self.book.category_totals(year=year, kind=kind, month=month)
        if not data:
            self.ax.text(0.5, 0.5, "No data to chart", ha="center", va="center", fontsize=12)
        else:
            labels, sizes = zip(*data)
            self.ax.pie(
                sizes,
                labels=labels,
                autopct=lambda p: f"{p:.0f}%\n" if p >= 6 else "",
                startangle=90,
                pctdistance=0.8,
                textprops={"fontsize": 8},
            )
            scope = "All months" if month is None else month_name
            self.ax.set_title(f"{kind.capitalize()} by category — {scope} {year}")

        self.ax.axis("equal")
        self.canvas.draw_idle()

    def save(self):
        save_book(self.book)
        messagebox.showinfo("Saved", "Your data has been saved.")

if __name__ == "__main__":
    app = FinanceApp()
    app.mainloop()
