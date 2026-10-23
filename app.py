"""Bilingual Tk UI. Worker threads communicate through a bounded queue. 双语线程安全界面。"""

from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
import webbrowser

from i18n import STATUS_KEYS, Translator, record_detail
import recover


POLL_INTERVAL_MS = 100
MAX_PENDING_EVENTS = 1000
MAX_HISTORY_BYTES = 64 * recover.MIB
OPENABLE_EXTENSIONS = {
    ".jpg", ".png", ".gif", ".bmp", ".webp", ".ico", ".tif", ".avif", ".heic",
    ".wav", ".mp3", ".flac", ".aac", ".amr", ".ogg", ".opus", ".aiff", ".au", ".m4a",
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".3gp",
}


class RecoveryApp:
    """One shared application for both editions. 中英文版本共用同一实现。"""

    def __init__(self, root: tk.Tk, language: str = "zh") -> None:
        self.root = root
        self.translate = Translator(language)
        width = min(1480, int(root.winfo_screenwidth() * 0.92))
        height = min(980, int(root.winfo_screenheight() * 0.90))
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(min(980, width), min(680, height))
        self.font_size = 14
        self.configure_fonts()
        self.source_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.max_file_mib = tk.StringVar(value="4096")
        self.verify_timeout = tk.StringVar(value="120")
        self.verify_enabled = tk.BooleanVar(value=True)
        self.status_text = tk.StringVar()
        self.filter_status = tk.StringVar()
        self.format_vars = {kind: tk.BooleanVar(value=True) for kind in recover.PUBLIC_TYPES}
        self.events = queue.Queue(maxsize=MAX_PENDING_EVENTS)  # Bounded memory. / 限制队列内存。
        self.cancel_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.directory: Path | None = None
        self.records: list[dict] = []
        self.displayed_records: dict[str, dict] = {}
        self.preview_photo = None
        self.closing = False
        self.build_interface()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(POLL_INTERVAL_MS, self.process_events)

    def notify(self, kind: str, title: str, message: str, **values):
        """Translate only application text, not paths or filenames. 仅翻译程序文字。"""
        return getattr(messagebox, kind)(self.translate(title), self.translate(message, **values), parent=self.root)

    def build_interface(self) -> None:
        t = self.translate
        self.root.title(t("Media Recovery | Read-only image scanner"))
        self.status_text.set(t("Select an image. Do not write anything to the physical disk with lost data."))
        self.filter_status.set(t("All"))
        self.build_menu()
        viewport = ttk.Frame(self.root)
        viewport.pack(fill="both", expand=True)
        canvas = tk.Canvas(viewport, highlightthickness=0)
        page_scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=page_scrollbar.set)
        page_scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        container = ttk.Frame(canvas, padding=16)
        window = canvas.create_window((0, 0), window=container, anchor="nw")

        def update_viewport(event=None):
            canvas.itemconfigure(window, width=canvas.winfo_width(),
                                 height=max(canvas.winfo_height(), container.winfo_reqheight()))
            canvas.configure(scrollregion=canvas.bbox("all"))

        canvas.bind("<Configure>", update_viewport)
        container.bind("<Configure>", update_viewport)  # Small displays can scroll the whole page. / 小屏可滚动整页。
        paths = ttk.LabelFrame(container, text=t("Source and destination"), padding=12)
        paths.pack(fill="x")
        for row, label, variable, command in (
            (0, "Source image (read-only)", self.source_path, self.choose_source),
            (1, "Safe output folder", self.output_path, self.choose_output),
        ):
            ttk.Label(paths, text=t(label)).grid(row=row, column=0, sticky="w", padx=4, pady=4)
            ttk.Entry(paths, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=4)
            ttk.Button(paths, text=t("Browse..."), command=command).grid(row=row, column=2, padx=4)
        paths.columnconfigure(1, weight=1)
        formats = ttk.Notebook(container)
        formats.pack(fill="x", pady=10)
        for group, kinds in recover.FORMAT_GROUPS.items():
            page = ttk.Frame(formats, padding=8)
            formats.add(page, text=t(group))
            for index, kind in enumerate(kinds):
                ttk.Checkbutton(page, text=kind.upper(), variable=self.format_vars[kind]).grid(
                    row=index // 4, column=index % 4, sticky="w", padx=12)
            for column in range(4):
                page.columnconfigure(column, weight=1)
        options = ttk.Frame(container)
        options.pack(fill="x")
        ttk.Button(options, text=t("Select all"), command=lambda: self.select_formats(True)).grid(row=0, column=0, padx=4, pady=4)
        ttk.Button(options, text=t("Clear"), command=lambda: self.select_formats(False)).grid(row=0, column=1, padx=4)
        ttk.Checkbutton(options, text=t("Verify after recovery"), variable=self.verify_enabled).grid(row=0, column=2, columnspan=2, sticky="w", padx=12)
        ttk.Label(options, text=t("Max file MiB")).grid(row=1, column=0, sticky="w", padx=4, pady=6)
        ttk.Entry(options, textvariable=self.max_file_mib, width=8).grid(row=1, column=1, sticky="w")
        ttk.Label(options, text=t("Timeout (seconds)")).grid(row=1, column=2, sticky="w", padx=12)
        ttk.Entry(options, textvariable=self.verify_timeout, width=7).grid(row=1, column=3, sticky="w")
        actions = ttk.Frame(container)
        actions.pack(fill="x", pady=8)
        self.scan_button = ttk.Button(actions, text=t("Read-only scan"), command=lambda: self.start(True))
        self.scan_button.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        self.recover_button = ttk.Button(actions, text=t("Recover and check"), command=lambda: self.start(False))
        self.recover_button.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        self.stop_button = ttk.Button(actions, text=t("Stop"), command=self.stop, state="disabled")
        self.stop_button.grid(row=0, column=2, sticky="ew", padx=4, pady=4)
        ttk.Button(actions, text=t("Open image gallery"), command=self.open_gallery).grid(row=1, column=0, sticky="ew", padx=4)
        ttk.Button(actions, text=t("Open results folder"), command=self.open_directory).grid(row=1, column=1, sticky="ew", padx=4)
        text_controls = ttk.Frame(actions)
        text_controls.grid(row=1, column=2, sticky="e")
        ttk.Button(text_controls, text="A−", width=4, command=lambda: self.change_font_size(-1)).pack(side="left", padx=2)
        ttk.Button(text_controls, text="A+", width=4, command=lambda: self.change_font_size(1)).pack(side="left", padx=2)
        for column in range(3):
            actions.columnconfigure(column, weight=1)
        self.progress = ttk.Progressbar(container, maximum=100)
        self.progress.pack(fill="x")
        status_label = ttk.Label(container, textvariable=self.status_text, wraplength=900)
        status_label.pack(fill="x", pady=6)
        status_label.bind("<Configure>", lambda event: status_label.configure(wraplength=max(200, event.width - 12)))
        result_bar = ttk.Frame(container)
        result_bar.pack(fill="x")
        ttk.Label(result_bar, text=t("Filter:")).pack(side="left")
        selector = ttk.Combobox(result_bar, textvariable=self.filter_status, state="readonly", width=21,
                                values=[t("All"), *(t.status(status) for status in STATUS_KEYS)])
        selector.pack(side="left")
        selector.bind("<<ComboboxSelected>>", lambda event: self.refresh_results())
        explanation = ttk.Label(container, text=t("OK means the specified check passed, not proof of original integrity."), wraplength=900)
        explanation.pack(fill="x", pady=4)
        explanation.bind("<Configure>", lambda event: explanation.configure(wraplength=max(200, event.width - 12)))
        results = ttk.Panedwindow(container, orient="horizontal", height=260)
        results.pack(fill="both", expand=True, pady=6)
        table_frame = ttk.Frame(results)
        self.table = ttk.Treeview(table_frame, columns=("status", "name", "size"), show="headings", selectmode="browse")
        for column, title, width in (("status", "Status", 150), ("name", "Recovered filename", 380), ("size", "Size", 95)):
            self.table.heading(column, text=t(title))
            self.table.column(column, width=width)
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        horizontal = ttk.Scrollbar(table_frame, orient="horizontal", command=self.table.xview)
        self.table.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        for status, color in (("OK", "#168046"), ("DAMAGED", "#c03333"), ("UNVERIFIED", "#916100")):
            self.table.tag_configure(status, foreground=color)
        self.table.bind("<<TreeviewSelect>>", self.show_preview)
        self.table.bind("<Double-1>", lambda event: self.open_selected())
        results.add(table_frame, weight=3)
        preview_frame = ttk.LabelFrame(results, text=t("Image preview / verification details"), padding=10)
        self.preview_label = ttk.Label(preview_frame, text=t("Select a result to preview it."), anchor="center", wraplength=320)
        self.preview_label.pack(fill="both", expand=True)
        self.detail_label = ttk.Label(preview_frame, text="", wraplength=340)
        self.detail_label.pack(fill="x", pady=8)
        preview_frame.bind("<Configure>", lambda event: self.detail_label.configure(wraplength=max(180, event.width - 24)))
        results.add(preview_frame, weight=1)
        self.log_text = tk.Text(container, height=3, wrap="word", state="disabled", font="TkFixedFont", padx=10, pady=8)
        self.log_text.pack(fill="x")

    def configure_fonts(self) -> None:
        """Point sizes follow Tk DPI scaling. 点字号遵循 Tk 的 DPI 缩放。"""
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont"):
            tkfont.nametofont(name, root=self.root).configure(size=self.font_size)
        tkfont.nametofont("TkHeadingFont", root=self.root).configure(size=self.font_size, weight="bold")
        tkfont.nametofont("TkFixedFont", root=self.root).configure(size=max(11, self.font_size - 1))
        style = ttk.Style(self.root)
        style.configure(".", font="TkDefaultFont")
        style.configure("TButton", padding=(12, 8))
        style.configure("TCheckbutton", padding=(6, 5))
        style.configure("TNotebook.Tab", padding=(16, 8))
        line_height = tkfont.nametofont("TkDefaultFont", root=self.root).metrics("linespace")
        style.configure("Treeview", font="TkDefaultFont", rowheight=line_height + 16)
        style.configure("Treeview.Heading", font="TkHeadingFont", padding=(8, 8))
        self.root.option_add("*Font", "TkDefaultFont")

    def change_font_size(self, amount: int = 0) -> None:
        self.font_size = max(11, min(22, self.font_size + amount)) if amount else 14
        self.configure_fonts()  # Keep tasks and results intact. / 保留任务及结果。

    def build_menu(self) -> None:
        t = self.translate
        menu = tk.Menu(self.root)
        sections = {
            "File": [("Select disk image...", self.choose_source), ("Select output folder...", self.choose_output),
                     ("Load previous manifest...", self.load_results), ("Open results folder", self.open_directory), ("Exit", self.close)],
            "Recovery": [("Scan without exporting", lambda: self.start(True)), ("Recover and check", lambda: self.start(False)), ("Stop task", self.stop)],
            "Preview": [("Open image gallery", self.open_gallery), ("Open selected media...", self.open_selected)],
            "Language": [("English", lambda: self.change_language("en")), ("Chinese", lambda: self.change_language("zh"))],
            "Text size": [("Larger text", lambda: self.change_font_size(1)), ("Smaller text", lambda: self.change_font_size(-1)), ("Reset text size", self.change_font_size)],
            "Help": [("Required libraries", self.show_dependencies), ("Formats and limitations", self.show_limits)],
        }
        for section, commands in sections.items():
            submenu = tk.Menu(menu, tearoff=False)
            for label, command in commands:
                submenu.add_command(label=t(label), command=command)
            menu.add_cascade(label=t(section), menu=submenu)
        self.root.config(menu=menu)

    def change_language(self, language: str) -> None:
        if self.is_running() or not self.events.empty():
            self.notify("showinfo", "Language change", "Stop the task before changing the interface language.")
            return
        self.translate = Translator(language)
        for child in self.root.winfo_children():
            child.destroy()
        self.build_interface()  # Rebuild labels, keep settings/results. / 重建文字，保留设置和结果。
        self.refresh_results()

    def is_running(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def choose_source(self) -> None:
        t = self.translate
        path = filedialog.askopenfilename(parent=self.root, title=t("Select a raw sector-by-sector image"),
                                         filetypes=[(t("Raw images"), "*.img *.dd *.raw *.bin"), (t("All files"), "*.*")])
        if path:
            self.source_path.set(path)

    def choose_output(self) -> None:
        path = filedialog.askdirectory(parent=self.root, title=self.translate("Select a folder on a different, healthy physical disk"))
        if path:
            self.output_path.set(path)

    def select_formats(self, selected: bool) -> None:
        for variable in self.format_vars.values():
            variable.set(selected)

    def start(self, dry_run: bool) -> None:
        if self.is_running():
            self.notify("showinfo", "Task running", "Stop the current task first.")
            return
        source = Path(self.source_path.get().strip().strip('"'))
        if not source.is_file():
            self.notify("showerror", "Invalid source", "Select a regular raw image file, not a drive letter or device.")
            return
        selected = [kind for kind, variable in self.format_vars.items() if variable.get()]
        if not selected:
            self.notify("showerror", "No formats selected", "Select at least one format.")
            return
        try:
            maximum, timeout = int(self.max_file_mib.get()), int(self.verify_timeout.get())
            if maximum <= 0 or timeout <= 0:
                raise ValueError()
        except ValueError:
            self.notify("showerror", "Invalid settings", "File limit and timeout must be positive integers.")
            return
        arguments = [str(source), "--types", ",".join(selected), "--max-file-mib", str(maximum),
                     "--verify-timeout", str(timeout), "--language", self.translate.language]
        if dry_run:
            arguments.append("--dry-run")
        else:
            if not self.output_path.get().strip():
                self.choose_output()
            if not self.output_path.get().strip():
                return
            if not self.notify("askyesno", "Confirm safe destination", "Are the program, image and output folder all on disks OTHER than the physical disk with lost data?\n\nDifferent drive letters do not necessarily mean different disks. This program cannot determine that for you."):
                return
            arguments.extend(["--output", self.output_path.get().strip().strip('"')])
            if not self.verify_enabled.get():
                arguments.append("--no-verify")
        self.records.clear()
        self.directory = None
        self.refresh_results()
        self.progress["value"] = 0
        self.cancel_event.clear()
        self.scan_button.configure(state="disabled")
        self.recover_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status_text.set(self.translate("Scanning read-only. Recovery and full decoding can take a long time..."))
        self.worker = threading.Thread(target=self.run_task, args=(arguments,), daemon=True)
        self.worker.start()

    def run_task(self, arguments: list[str]) -> None:
        def emit(kind, payload):
            self.events.put((kind, payload))  # Never access Tk here. / 工作线程不操作 Tk。
        try:
            code = recover.main(arguments, log=lambda value: emit("log", value),
                                on_record=lambda value: emit("record", value),
                                on_directory=lambda value: emit("directory", value),
                                progress=lambda position, size: emit("progress", (position, size)),
                                cancel_event=self.cancel_event)
            emit("done", code)
        except Exception as error:
            emit("log", self.translate("Task exception: {error}", error=error))
            emit("done", 1)

    def process_events(self) -> None:
        for _ in range(150):
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.log_text.configure(state="normal")
                self.log_text.insert("end", payload + "\n")
                if int(self.log_text.index("end-1c").split(".")[0]) > 500:
                    self.log_text.delete("1.0", "101.0")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
            elif kind == "directory":
                self.directory = payload
            elif kind == "record":
                self.records.append(payload)
                self.add_result(payload)
            elif kind == "progress":
                position, size = payload
                self.progress["value"] = 100 * position / size if size else 100
            elif kind == "done":
                self.scan_button.configure(state="normal")
                self.recover_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
                counts = {status: sum(record.get("status") == status for record in self.records) for status in STATUS_KEYS}
                state = self.translate({0: "Complete", 130: "Stopped"}.get(payload, "Error; see the log"))
                self.status_text.set(self.translate("{state} | Verified: {ok} | Damage detected: {damaged} | Not fully verified: {unverified}",
                                                    state=state, ok=counts["OK"], damaged=counts["DAMAGED"], unverified=counts["UNVERIFIED"]))
        if self.closing and not self.is_running():
            self.root.destroy()
            return
        self.root.after(POLL_INTERVAL_MS, self.process_events)

    def add_result(self, record: dict) -> None:
        status = record.get("status", "UNVERIFIED")
        if self.filter_status.get() not in (self.translate("All"), self.translate.status(status)):
            return
        item = self.table.insert("", "end", values=(self.translate.status(status), record["file"],
                                                       f"{record['size'] / recover.MIB:.2f} MiB"), tags=(status,))
        self.displayed_records[item] = record

    def refresh_results(self) -> None:
        children = self.table.get_children()
        if children:
            self.table.delete(*children)
        self.displayed_records.clear()
        self.preview_photo = None
        self.preview_label.configure(image="", text=self.translate("Select a result to preview it."))
        self.detail_label.configure(text="")
        for record in self.records:
            self.add_result(record)

    def selected_record(self) -> dict | None:
        selection = self.table.selection()
        return self.displayed_records.get(selection[0]) if selection else None

    def show_preview(self, event=None) -> None:
        record = self.selected_record()
        if record is None:
            return
        self.preview_photo = None
        self.preview_label.configure(image="", text=self.translate("No image preview for this result."))
        self.detail_label.configure(text=record_detail(record, self.translate.language))
        if record.get("preview"):
            path = self.safe_result_path(record["preview"])
            if path is not None and path.is_file():
                try:
                    # Load only our generated thumbnail. / 不在主线程解码恢复出的原图。
                    self.preview_photo = tk.PhotoImage(file=str(path))
                    self.preview_label.configure(image=self.preview_photo, text="")
                except tk.TclError:
                    self.preview_label.configure(text=self.translate("Cannot load the preview. Try the gallery."))

    def safe_result_path(self, relative: str) -> Path | None:
        if self.directory is None or not isinstance(relative, str):
            return None
        path = (self.directory / relative).resolve()
        return path if path.is_relative_to(self.directory.resolve()) else None

    def open_directory(self) -> None:
        if self.directory is not None and self.directory.is_dir():
            self.open_path(self.directory)
        else:
            self.notify("showinfo", "No results yet", "Recover files or load a previous manifest first.")

    def open_gallery(self) -> None:
        if self.directory is not None:
            localized = self.directory / f"preview_{self.translate.language}.html"
            target = localized if localized.is_file() else self.directory / "preview.html"
            if target.is_file():
                webbrowser.open(target.resolve().as_uri())
                return
        self.notify("showinfo", "Gallery not ready", "The gallery is generated when the task finishes or stops.")

    def open_selected(self) -> None:
        record = self.selected_record()
        if record is None:
            return
        path = self.safe_result_path(record["file"])
        if path is None or not path.is_file():
            self.notify("showerror", "Missing file", "The result does not exist or its path is unsafe.")
            return
        if path.suffix.lower() not in OPENABLE_EXTENSIONS:
            self.notify("showinfo", "Safety notice", "Only image/audio/video files can be opened here. Inspect other recovered files safely yourself.")
            return
        if self.notify("askyesno", "Open recovered media", "The system viewer will open this file. Recovered files may be damaged or untrusted. Continue?"):
            self.open_path(path)

    def open_path(self, path: Path) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as error:
            messagebox.showerror(self.translate("Cannot open"), str(error), parent=self.root)

    def load_results(self) -> None:
        if self.is_running():
            self.notify("showinfo", "Task running", "Stop the current task first.")
            return
        filename = filedialog.askopenfilename(parent=self.root, title=self.translate("Select manifest.jsonl"),
                                             filetypes=[(self.translate("Recovery manifest"), "*.jsonl")])
        if not filename:
            return
        try:
            path = Path(filename)
            if path.stat().st_size > MAX_HISTORY_BYTES:
                raise ValueError(self.translate("The manifest contains an invalid record."))
            records = []
            with path.open(encoding="utf-8") as source:
                for line in source:
                    entry = json.loads(line)
                    if not isinstance(entry, dict):
                        raise ValueError(self.translate("The manifest contains an invalid record."))
                    if entry.get("event") == "recovered":
                        if (not isinstance(entry.get("file"), str) or not isinstance(entry.get("size"), int)
                                or entry["size"] < 0 or entry.get("status", "UNVERIFIED") not in STATUS_KEYS
                                or any(not isinstance(entry[key], str) for key in ("detail", "detail_en", "detail_zh", "preview") if key in entry)):
                            raise ValueError(self.translate("The manifest contains an invalid record."))
                        records.append(entry)
            self.directory, self.records = path.parent, records
            self.refresh_results()
            self.status_text.set(self.translate("Loaded {count} previous records. This does not re-verify the files.", count=len(records)))
        except (OSError, ValueError, TypeError) as error:
            messagebox.showerror(self.translate("Cannot read manifest"), str(error), parent=self.root)

    def show_dependencies(self) -> None:
        t = self.translate
        messagebox.showinfo(t("Required libraries"), t("Required: Pillow, miniaudio, pillow-heif. Install requirements.txt before starting. Libraries are imported directly; no missing-library fallback is provided. No external FFmpeg is used. Videos receive structural checks only."), parent=self.root)

    def show_limits(self) -> None:
        self.notify("showinfo", "Limitations", "Only contiguous data in raw images is carved; the source is opened read-only.\nNo original names, disk-fragment reassembly, repair or guaranteed recovery.\nVideo structure only; no video decoder is used.")

    def stop(self) -> None:
        if self.is_running():
            self.cancel_event.set()
            self.status_text.set(self.translate("Stopping; completed results will be kept..."))

    def close(self) -> None:
        if self.is_running():
            if not self.notify("askyesno", "Stop and exit", "Stop the running task and exit? Completed results will be kept."):
                return
            self.closing = True
            self.stop()
        else:
            self.root.destroy()


def launch(language: str = "zh") -> None:
    root = tk.Tk()
    RecoveryApp(root, language)
    root.mainloop()


if __name__ == "__main__":
    launch()
