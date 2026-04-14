# gui.py

import threading
import concurrent.futures
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from searcher import DatasheetDownloader
import config


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Datasheet Downloader")
        self.geometry("1100x700")
        self.minsize(980, 620)

        self.parts = []
        self.selected = set()
        self.part_buttons = {}
        self.downloader = None
        self.worker_thread = None

        self.out_dir_var = tk.StringVar(value=str(Path.cwd() / "datasheets"))
        self.status_var = tk.StringVar(value="Готово")

        self._build_ui()

    def _build_ui(self):
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)

        # Верхняя панель
        top = ttk.Frame(root)
        top.pack(fill="x", pady=(0, 10))

        ttk.Label(top, text="Папка для сохранения:").pack(side="left")
        ttk.Entry(top, textvariable=self.out_dir_var, width=55).pack(side="left", padx=8)
        ttk.Button(top, text="Выбрать…", command=self.choose_out_dir).pack(side="left")

        ttk.Button(top, text="Загрузить TXT", command=self.load_txt).pack(side="right", padx=(8, 0))
        ttk.Button(top, text="Вставить список", command=self.import_from_text).pack(side="right")

        # Основная область
        center = ttk.Panedwindow(root, orient="horizontal")
        center.pack(fill="both", expand=True)

        left = ttk.Frame(center, padding=(0, 0, 8, 0))
        right = ttk.Frame(center, padding=(8, 0, 0, 0))
        center.add(left, weight=3)
        center.add(right, weight=2)

        input_frame = ttk.LabelFrame(left, text="Список наименований")
        input_frame.pack(fill="x", pady=(0, 10))

        self.input_text = tk.Text(input_frame, height=6, wrap="word")
        self.input_text.pack(fill="x", padx=8, pady=8)

        btns = ttk.Frame(input_frame)
        btns.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btns, text="Сформировать кнопки", command=self.build_buttons_from_text).pack(side="left")
        ttk.Button(btns, text="Очистить выделение", command=self.clear_selection).pack(side="left", padx=8)
        ttk.Button(btns, text="Выбрать все", command=self.select_all).pack(side="left")

        buttons_frame = ttk.LabelFrame(left, text="Нажмите на нужные позиции")
        buttons_frame.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(buttons_frame, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(buttons_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable = ttk.Frame(self.canvas)

        self.scrollable.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        self.scrollbar.pack(side="right", fill="y", pady=8)

        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        right_top = ttk.LabelFrame(right, text="Выбрано")
        right_top.pack(fill="both", expand=True)

        self.selected_list = tk.Listbox(right_top, height=15, selectmode="extended")
        self.selected_list.pack(fill="both", expand=True, padx=8, pady=8)

        sel_btns = ttk.Frame(right_top)
        sel_btns.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(sel_btns, text="Убрать выбранное", command=self.remove_selected_from_list).pack(side="left")
        ttk.Button(sel_btns, text="Скачать datasheets", command=self.start_download).pack(side="right")

        log_frame = ttk.LabelFrame(right, text="Лог")
        log_frame.pack(fill="both", expand=True, pady=(10, 0))

        self.log_text = tk.Text(log_frame, height=12, wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=8, pady=8)

        bottom = ttk.Frame(root)
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Label(bottom, textvariable=self.status_var).pack(side="left")
        ttk.Button(bottom, text="Стоп (не реализован)", state="disabled").pack(side="right")

    def _on_canvas_resize(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        try:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def log(self, msg: str):
        def append():
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
        self.after(0, append)

    def set_status(self, msg: str):
        self.after(0, lambda: self.status_var.set(msg))

    def choose_out_dir(self):
        folder = filedialog.askdirectory(initialdir=self.out_dir_var.get() or str(Path.cwd()))
        if folder:
            self.out_dir_var.set(folder)

    def load_txt(self):
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            self.input_text.delete("1.0", "end")
            self.input_text.insert("1.0", text)
            self.log(f"Загружен файл: {path}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def import_from_text(self):
        text = self.input_text.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Пусто", "Вставьте список наименований.")
            return
        self.parts = [line.strip() for line in text.splitlines() if line.strip()]
        self.selected.clear()
        self.build_buttons()
        self.refresh_selected_list()
        self.log(f"Импортировано позиций: {len(self.parts)}")

    def build_buttons_from_text(self):
        self.import_from_text()

    def clear_selection(self):
        self.selected.clear()
        self.refresh_selected_list()
        self.update_button_states()

    def select_all(self):
        self.selected = set(self.parts)
        self.refresh_selected_list()
        self.update_button_states()

    def remove_selected_from_list(self):
        idxs = list(self.selected_list.curselection())
        if not idxs:
            return
        current = list(self.selected)
        for i in reversed(idxs):
            if 0 <= i < len(current):
                self.selected.discard(current[i])
        self.refresh_selected_list()
        self.update_button_states()

    def build_buttons(self):
        for widget in self.scrollable.winfo_children():
            widget.destroy()
        self.part_buttons.clear()

        cols = 3
        for i, part in enumerate(self.parts):
            row = i // cols
            col = i % cols
            btn = ttk.Button(self.scrollable, text=part, command=lambda p=part: self.toggle_part(p))
            btn.grid(row=row, column=col, sticky="ew", padx=6, pady=6)
            self.part_buttons[part] = btn

        for c in range(cols):
            self.scrollable.columnconfigure(c, weight=1)

        self.update_button_states()

    def toggle_part(self, part: str):
        if part in self.selected:
            self.selected.remove(part)
        else:
            self.selected.add(part)
        self.refresh_selected_list()
        self.update_button_states()

    def update_button_states(self):
        for part, btn in self.part_buttons.items():
            try:
                if part in self.selected:
                    btn.state(["pressed"])
                else:
                    btn.state(["!pressed"])
            except Exception:
                pass

    def refresh_selected_list(self):
        self.selected_list.delete(0, "end")
        for item in sorted(self.selected):
            self.selected_list.insert("end", item)
        self.update_button_states()

    def start_download(self):
        if not self.selected:
            messagebox.showwarning("Нет выбора", "Выберите хотя бы одну позицию.")
            return

        out_dir = Path(self.out_dir_var.get().strip() or "datasheets")
        out_dir.mkdir(parents=True, exist_ok=True)

        self.downloader = DatasheetDownloader(out_dir, log_callback=self.log)
        parts_to_download = list(sorted(self.selected))

        self.status_var.set(f"Скачивание: {len(parts_to_download)} позиций (параллельно до {config.MAX_WORKERS_TOTAL})")
        self.log("=== Старт параллельной загрузки ===")

        def process_part(part: str) -> bool:
            try:
                return self.downloader.find_and_download_datasheet(part)
            except Exception as e:
                self.log(f"  критическая ошибка для {part}: {e}")
                return False

        def worker():
            ok = 0
            total = len(parts_to_download)
            with concurrent.futures.ThreadPoolExecutor(max_workers=config.MAX_WORKERS_TOTAL) as executor:
                future_to_part = {
                    executor.submit(process_part, part): part
                    for part in parts_to_download
                }
                for future in concurrent.futures.as_completed(future_to_part):
                    part = future_to_part[future]
                    try:
                        success = future.result()
                        if success:
                            ok += 1
                        completed = len(future_to_part) - len([f for f in future_to_part if not f.done()])
                        self.set_status(f"Скачивание: {completed}/{total} завершено")
                    except Exception as e:
                        self.log(f"Ошибка в потоке для {part}: {e}")

            self.log(f"=== Готово: {ok}/{total} скачано ===")
            self.set_status(f"Готово: {ok}/{total} скачано")

        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()