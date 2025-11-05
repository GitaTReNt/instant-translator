from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QLabel, QMenuBar, QDialog,
    QFormLayout, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QDialogButtonBox, QCheckBox, QFileDialog, QMessageBox, QTextBrowser, QPushButton, QHBoxLayout
)
import queue, time
from settings import load_settings, save_settings
from asr_engine import AsrEngine
from srt_writer import TxtWriter, SrtWriter

LANGS = [
    ("zh", "中文 (ZH)"),
    ("ja", "日本語 (JA)"),
    ("es", "Español (ES)"),
    ("fr", "Français (FR)"),
    ("de", "Deutsch (DE)"),
    ("ko", "한국어 (KO)"),
    ("EN-US", "English (US)"),
    ("EN-GB", "English (UK)")
]

class Overlay(QWidget):
    def __init__(self, max_lines=10, font_src=18, font_tgt=22):
        super().__init__()
        self.setWindowTitle("GuiLiveSubs Overlay")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(QSize(800, 220))

        self.src_view = QTextBrowser(self)
        self.tgt_view = QTextBrowser(self)
        self.src_view.setReadOnly(True)
        self.tgt_view.setReadOnly(True)
        self.src_view.setStyleSheet("background: transparent; color: white;")
        self.tgt_view.setStyleSheet("background: transparent; color: white;")
        self.src_view.setFont(QFont("Segoe UI", font_src))
        self.tgt_view.setFont(QFont("Segoe UI", font_tgt))

        wrapper = QWidget(self)
        wrapper.setStyleSheet("background: rgba(0,0,0,0.72); border-radius: 16px;")
        lay = QVBoxLayout(wrapper)
        lay.setContentsMargins(24,18,24,18)
        lay.setSpacing(8)
        lay.addWidget(self.src_view)
        lay.addWidget(self.tgt_view)

        root = QVBoxLayout(self)
        root.setContentsMargins(0,0,0,0)
        root.addWidget(wrapper)

        self.max_lines = max_lines
        self.show_source = True

    def set_fonts(self, src_sz: int, tgt_sz: int):
        self.src_view.setFont(QFont("Segoe UI", src_sz))
        self.tgt_view.setFont(QFont("Segoe UI", tgt_sz))

    def set_show_source(self, show: bool):
        self.show_source = show
        self.src_view.setVisible(show)

    def append(self, src: str, tgt: str):
        if self.show_source and src:
            self._append_text(self.src_view, src)
        if tgt:
            self._append_text(self.tgt_view, tgt)

    def _append_text(self, view: QTextBrowser, text: str):
        cur = view.toPlainText().splitlines()
        cur.append(text.strip())
        cur = cur[-self.max_lines:]
        view.setPlainText("\n".join(cur))
        view.moveCursor(view.textCursor().End)

    def mousePressEvent(self, e):
        self._drag = e.globalPosition()

    def mouseMoveEvent(self, e):
        if hasattr(self, "_drag"):
            delta = e.globalPosition() - self._drag
            self.move(self.pos() + delta.toPoint())
            self._drag = e.globalPosition()

class Prefs(QDialog):
    def __init__(self, data):
        super().__init__()
        self.setWindowTitle("Preferences")
        self.data = data.copy()
        form = QFormLayout(self)

        self.ed_key = QLineEdit(self.data.get("deepl_key",""))
        self.ed_key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("DeepL API Key:", self.ed_key)

        self.cb_lang = QComboBox()
        for code,label in LANGS:
            self.cb_lang.addItem(label, code)
        idx = next((i for i,(c,_) in enumerate(LANGS) if c==self.data.get("target_lang","zh")), 0)
        self.cb_lang.setCurrentIndex(idx)
        form.addRow("Target Language:", self.cb_lang)

        self.sp_src = QSpinBox(); self.sp_src.setRange(10, 64); self.sp_src.setValue(int(self.data.get("font_size_src",18)))
        self.sp_tgt = QSpinBox(); self.sp_tgt.setRange(10, 72); self.sp_tgt.setValue(int(self.data.get("font_size_tgt",22)))
        form.addRow("Font size (source):", self.sp_src)
        form.addRow("Font size (target):", self.sp_tgt)

        self.sp_lines = QSpinBox(); self.sp_lines.setRange(1, 100); self.sp_lines.setValue(int(self.data.get("max_lines",10)))
        form.addRow("Max lines (rolling):", self.sp_lines)

        self.chk_show_src = QCheckBox("Show source (English) line")
        self.chk_show_src.setChecked(bool(self.data.get("show_source", True)))
        form.addRow(self.chk_show_src)

        self.chk_txt = QCheckBox("Save translation to TXT")
        self.chk_txt.setChecked(bool(self.data.get("save_txt", False)))
        self.ed_txt = QLineEdit(self.data.get("save_txt_path",""))
        self.btn_txt = QPushButton("Browse…")
        def pick_txt():
            path,_ = QFileDialog.getSaveFileName(self, "Choose TXT File", "", "Text Files (*.txt);;All Files (*)")
            if path:
                self.ed_txt.setText(path)
        self.btn_txt.clicked.connect(pick_txt)

        self.chk_srt = QCheckBox("Save captions to SRT")
        self.chk_srt.setChecked(bool(self.data.get("save_srt", False)))
        self.ed_srt = QLineEdit(self.data.get("save_srt_path",""))
        self.btn_srt = QPushButton("Browse…")
        def pick_srt():
            path,_ = QFileDialog.getSaveFileName(self, "Choose SRT File", "", "SubRip (*.srt);;All Files (*)")
            if path:
                self.ed_srt.setText(path)
        self.btn_srt.clicked.connect(pick_srt)

        row1 = QHBoxLayout(); row1.addWidget(self.chk_txt); row1.addWidget(self.ed_txt); row1.addWidget(self.btn_txt)
        row2 = QHBoxLayout(); row2.addWidget(self.chk_srt); row2.addWidget(self.ed_srt); row2.addWidget(self.btn_srt)
        form.addRow(row1); form.addRow(row2)

        self.cb_device = QComboBox()
        for d in ["cpu", "cuda", "auto"]:
            self.cb_device.addItem(d, d)
        dv = self.data.get("device","cpu")
        self.cb_device.setCurrentIndex(["cpu","cuda","auto"].index(dv) if dv in ["cpu","cuda","auto"] else 0)
        form.addRow("Device:", self.cb_device)

        self.cb_compute = QComboBox()
        for c in ["int8","float32","float16"]:
            self.cb_compute.addItem(c, c)
        cv = self.data.get("compute_type","int8")
        self.cb_compute.setCurrentIndex(["int8","float32","float16"].index(cv) if cv in ["int8","float16","float32"] else 0)
        form.addRow("Compute Type:", self.cb_compute)

        self.sp_min = QSpinBox(); self.sp_min.setRange(200, 3000); self.sp_min.setValue(int(self.data.get("min_chunk_ms",600)))
        self.sp_sil = QSpinBox(); self.sp_sil.setRange(100, 2000); self.sp_sil.setValue(int(self.data.get("max_sil_ms",350)))
        self.sp_vad = QDoubleSpinBox(); self.sp_vad.setRange(1.0, 8.0); self.sp_vad.setSingleStep(0.1); self.sp_vad.setValue(float(self.data.get("vad_thresh_mult",2.5)))
        form.addRow("Min chunk (ms):", self.sp_min)
        form.addRow("Max silence (ms):", self.sp_sil)
        form.addRow("VAD threshold ×:", self.sp_vad)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def values(self):
        d = dict(
            deepl_key=self.ed_key.text().strip(),
            target_lang=self.cb_lang.currentData(),
            font_size_src=int(self.sp_src.value()),
            font_size_tgt=int(self.sp_tgt.value()),
            max_lines=int(self.sp_lines.value()),
            show_source=bool(self.chk_show_src.isChecked()),
            save_txt=bool(self.chk_txt.isChecked()),
            save_txt_path=self.ed_txt.text().strip(),
            save_srt=bool(self.chk_srt.isChecked()),
            save_srt_path=self.ed_srt.text().strip(),
            device=self.cb_device.currentData(),
            compute_type=self.cb_compute.currentData(),
            min_chunk_ms=int(self.sp_min.value()),
            max_sil_ms=int(self.sp_sil.value()),
            vad_thresh_mult=float(self.sp_vad.value())
        )
        return d

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GuiLiveSubs")
        self.resize(800, 480)
        self.data = load_settings()
        self.output_q = queue.Queue()
        self.engine = None
        self.overlay = Overlay(self.data.get("max_lines",10),
                               self.data.get("font_size_src",18),
                               self.data.get("font_size_tgt",22))
        self.overlay.set_show_source(self.data.get("show_source",True))

        bar = QMenuBar(self); self.setMenuBar(bar)
        m = bar.addMenu("GuiLiveSubs")
        act_prefs = QAction("Preferences…", self); act_prefs.triggered.connect(self.show_prefs); m.addAction(act_prefs)
        m.addSeparator()
        act_start = QAction("Start", self); act_start.triggered.connect(self.start); m.addAction(act_start)
        act_stop = QAction("Stop", self); act_stop.triggered.connect(self.stop); m.addAction(act_stop)
        m.addSeparator()
        act_overlay = QAction("Toggle Overlay", self); act_overlay.triggered.connect(self.toggle_overlay); m.addAction(act_overlay)

        lbl = QLabel("Steps:\n1) GuiLiveSubs → Preferences… 填写 DeepL API Key、设置语言/保存选项\n2) Start 开始；Toggle Overlay 显示/隐藏悬浮窗\n3) 可在偏好里调整滚动行数、字号、保存 TXT/SRT")
        lbl.setWordWrap(True)
        w = QWidget(); lay = QVBoxLayout(w); lay.addWidget(lbl); self.setCentralWidget(w)

        self.txt_writer = None
        self.srt_writer = None
        self.timer = QTimer(self); self.timer.setInterval(50); self.timer.timeout.connect(self._drain); self.timer.start()

    def show_prefs(self):
        dlg = Prefs(self.data)
        if dlg.exec():
            self.data = save_settings(dlg.values())
            self.overlay.set_show_source(self.data.get("show_source", True))
            self.overlay.set_fonts(self.data.get("font_size_src",18), self.data.get("font_size_tgt",22))
            self.statusBar().showMessage("Preferences saved", 2000)

    def start(self):
        if not self.data.get("deepl_key"):
            QMessageBox.warning(self, "Missing API Key", "请在 Preferences 里填写 DeepL API Key")
            return
        if self.engine:
            return
        if self.data.get("save_txt") and self.data.get("save_txt_path"):
            self.txt_writer = TxtWriter(self.data["save_txt_path"]); self.txt_writer.open()
        else:
            self.txt_writer = None
        if self.data.get("save_srt") and self.data.get("save_srt_path"):
            import time
            self.srt_writer = SrtWriter(self.data["save_srt_path"], session_start_monotonic=time.monotonic()); self.srt_writer.open()
        else:
            self.srt_writer = None

        self.engine = AsrEngine(
            output_q=self.output_q,
            deepl_key=self.data["deepl_key"],
            target_lang=self.data.get("target_lang","zh"),
            model_name=self.data.get("model_name","base.en"),
            device=self.data.get("device","cpu"),
            compute_type=self.data.get("compute_type","int8"),
            min_chunk_ms=int(self.data.get("min_chunk_ms",600)),
            max_sil_ms=int(self.data.get("max_sil_ms",350)),
            vad_thresh_mult=float(self.data.get("vad_thresh_mult",2.5)),
            api_base="https://api-free.deepl.com" if self.data.get("deepl_key","").endswith(":fx") else "https://api.deepl.com"
        )
        self.engine.start()
        self.overlay.show()
        self.statusBar().showMessage("Running…", 3000)

    def stop(self):
        if self.engine:
            self.engine.stop()
            self.engine = None
        if self.txt_writer:
            self.txt_writer.close(); self.txt_writer = None
        if self.srt_writer:
            self.srt_writer.close(); self.srt_writer = None
        self.statusBar().showMessage("Stopped.", 2000)

    def toggle_overlay(self):
        if self.overlay.isVisible():
            self.overlay.hide()
        else:
            self.overlay.show()

    def _drain(self):
        try:
            while True:
                item = self.output_q.get_nowait()
                src = item.get("src","")
                tgt = item.get("tgt","")
                st = item.get("start",0.0)
                et = item.get("end",0.0)
                self.overlay.append(src if self.data.get("show_source",True) else "", tgt)
                if self.txt_writer:
                    self.txt_writer.write_line(src if self.data.get("show_source",True) else "", tgt)
                if self.srt_writer:
                    self.srt_writer.write_caption(st, et, src if self.data.get("show_source",True) else "", tgt)
        except Exception:
            pass
