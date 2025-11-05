# app/ui.py
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QAction, QFont, QKeySequence, QShortcut, QIcon, QColor
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QLabel, QMenuBar, QDialog,
    QFormLayout, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QDialogButtonBox, QCheckBox, QFileDialog, QMessageBox, QTextBrowser,
    QPushButton, QHBoxLayout, QFrame, QToolButton, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QGuiApplication, QCursor
import queue, time
from settings import load_settings, save_settings
from asr_engine import AsrEngine
from srt_writer import TxtWriter, SrtWriter
from PyQt6.QtGui import QAction, QFont, QKeySequence, QShortcut, QIcon, QColor, QGuiApplication

# ----------- 语言列表 -----------
LANGS = [
    ("ZH", "中文 (ZH)"),
    ("JA", "日本語 (JA)"),
    ("ES", "Español (ES)"),
    ("FR", "Français (FR)"),
    ("DE", "Deutsch (DE)"),
    ("KO", "한국어 (KO)"),
    ("EN-US", "English (US)"),
    ("EN-GB", "English (UK)")
]

# ----------- 统一样式（深色、圆角、按钮）-----------
STYLE = """
QMainWindow { background-color: #0f172a; }                  /* slate-900 */
#HeroCard {
  background-color: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 18px;
}
QLabel#Title   { color: #e2e8f0; font-size: 26px; font-weight: 700; }
QLabel#Subtitle{ color: #94a3b8; font-size: 14px; }
QLabel#Summary { color: #a1a1aa; font-size: 12px; }
QToolButton {
  background-color: #1e293b;   /* slate-800 */
  color: #e2e8f0;
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 12px;
  padding: 10px 16px;
  font-size: 15px;
}
QToolButton:hover  { background-color: #334155; }
QToolButton:pressed{ background-color: #0ea5e9; color: #0b1020; } /* sky-500 */
QTextBrowser { background: transparent; color: white; border: 0; }
"""

# ================= Overlay（悬浮字幕窗口） =================
class Overlay(QWidget):
    BORDER = 8
    def __init__(self, max_lines=10, font_src=18, font_tgt=22):
        super().__init__()
        self.setWindowTitle("GuiLiveSubs Overlay")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(QSize(820, 240))

        self.src_view = QTextBrowser(self)
        self.tgt_view = QTextBrowser(self)
        self.src_view.setReadOnly(True)
        self.tgt_view.setReadOnly(True)
        self.src_view.setStyleSheet("background: transparent; color: #e2e8f0;")
        self.tgt_view.setStyleSheet("background: transparent; color: #ffffff;")
        self.src_view.setFont(QFont(self.font().family(), font_src))
        self.tgt_view.setFont(QFont(self.font().family(), font_tgt))

        wrapper = QFrame(self)
        wrapper.setObjectName("OverlayCard")
        wrapper.setStyleSheet("""
            #OverlayCard { background: rgba(10, 15, 28, 0.78); border-radius: 16px;
                           border: 1px solid rgba(255,255,255,0.08); }
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setColor(QColor(0,0,0,160))
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        wrapper.setGraphicsEffect(shadow)

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
        self.src_view.setFont(QFont(self.font().family(), src_sz))
        self.tgt_view.setFont(QFont(self.font().family(), tgt_sz))

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
        self._drag_pos = e.globalPosition().toPoint()
        self._orig_geom = self.geometry()
        L,R,T,B = self._hit_edges(e.position().toPoint())
        self._resizing = any([L,R,T,B])
        self._resize_edges = (L,R,T,B)
        if not self._resizing:
            # 普通拖动窗口
            self._moving = True
        return super().mousePressEvent(e)

    def resize_relative(self, w_ratio: float = 0.75, h_ratio: float = 0.10, bottom_margin: int = 20):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        w = int(screen.width() * w_ratio)
        h = int(screen.height() * h_ratio)
        x = screen.x() + (screen.width() - w) // 2
        y = screen.y() + screen.height() - h - bottom_margin
        self.setGeometry(x, y, w, h)

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        L,R,T,B = self._hit_edges(pos)

        if getattr(self, "_resizing", False):
            delta = e.globalPosition().toPoint() - self._drag_pos
            g = QRect(self._orig_geom)

            if self._resize_edges[0]:  # 左
                g.setLeft(g.left() + delta.x())
            if self._resize_edges[1]:  # 右
                g.setRight(g.right() + delta.x())
            if self._resize_edges[2]:  # 上
                g.setTop(g.top() + delta.y())
            if self._resize_edges[3]:  # 下
                g.setBottom(g.bottom() + delta.y())

            # 限制最小尺寸
            g.setWidth(max(g.width(), 600))
            g.setHeight(max(g.height(), 180))
            self.setGeometry(g)
        elif getattr(self, "_moving", False):
            delta = e.globalPosition().toPoint() - self._drag_pos
            self.move(self._orig_geom.topLeft() + delta)
        else:
            # 根据命中边缘改变鼠标指针
            if (L and T) or (R and B):
                QCursor.setShape(Qt.CursorShape.SizeFDiagCursor)
            elif (R and T) or (L and B):
                QCursor.setShape(Qt.CursorShape.SizeBDiagCursor)
            elif L or R:
                QCursor.setShape(Qt.CursorShape.SizeHorCursor)
            elif T or B:
                QCursor.setShape(Qt.CursorShape.SizeVerCursor)
            else:
                QCursor.setShape(Qt.CursorShape.ArrowCursor)

        return super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._resizing = False
        self._moving = False
        return super().mouseReleaseEvent(e)

    def _hit_edges(self, pos):
        r = self.rect()
        left  = abs(pos.x() - r.left())   <= self.BORDER
        right = abs(pos.x() - r.right())  <= self.BORDER
        top   = abs(pos.y() - r.top())    <= self.BORDER
        bot   = abs(pos.y() - r.bottom()) <= self.BORDER
        return left, right, top, bot

# ================= 偏好设置对话框 =================
class Prefs(QDialog):
    def __init__(self, data):
        super().__init__()
        self.setWindowTitle("Preferences")
        self.data = data.copy()
        form = QFormLayout(self)

        self.ed_key = QLineEdit(self.data.get("deepl_key","")); self.ed_key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("DeepL API Key:", self.ed_key)

        self.cb_lang = QComboBox()
        for code,label in LANGS: self.cb_lang.addItem(label, code)
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

        # Saving
        self.chk_txt = QCheckBox("Save translation to TXT"); self.chk_txt.setChecked(bool(self.data.get("save_txt", False)))
        self.ed_txt = QLineEdit(self.data.get("save_txt_path",""))
        self.btn_txt = QPushButton("Browse…")
        self.btn_txt.clicked.connect(lambda: self._pick_path(self.ed_txt, "Text Files (*.txt);;All Files (*)"))
        row1 = QHBoxLayout(); row1.addWidget(self.chk_txt); row1.addWidget(self.ed_txt); row1.addWidget(self.btn_txt); form.addRow(row1)

        self.chk_srt = QCheckBox("Save captions to SRT"); self.chk_srt.setChecked(bool(self.data.get("save_srt", False)))
        self.ed_srt = QLineEdit(self.data.get("save_srt_path",""))
        self.btn_srt = QPushButton("Browse…")
        self.btn_srt.clicked.connect(lambda: self._pick_path(self.ed_srt, "SubRip (*.srt);;All Files (*)"))
        row2 = QHBoxLayout(); row2.addWidget(self.chk_srt); row2.addWidget(self.ed_srt); row2.addWidget(self.btn_srt); form.addRow(row2)

        # Advanced
        self.cb_device = QComboBox(); [self.cb_device.addItem(d, d) for d in ["cpu","cuda","auto"]]
        dv = self.data.get("device","cpu")
        self.cb_device.setCurrentIndex(["cpu","cuda","auto"].index(dv) if dv in ["cpu","cuda","auto"] else 0)
        form.addRow("Device:", self.cb_device)

        self.cb_compute = QComboBox(); [self.cb_compute.addItem(c, c) for c in ["int8","float32","float16"]]
        cv = self.data.get("compute_type","int8")
        self.cb_compute.setCurrentIndex(["int8","float32","float16"].index(cv) if cv in ["int8","float32","float16"] else 0)
        form.addRow("Compute Type:", self.cb_compute)

        self.sp_min = QSpinBox(); self.sp_min.setRange(200, 3000); self.sp_min.setValue(int(self.data.get("min_chunk_ms",600)))
        self.sp_sil = QSpinBox(); self.sp_sil.setRange(100, 2000); self.sp_sil.setValue(int(self.data.get("max_sil_ms",350)))
        self.sp_vad = QDoubleSpinBox(); self.sp_vad.setRange(1.0, 8.0); self.sp_vad.setSingleStep(0.1); self.sp_vad.setValue(float(self.data.get("vad_thresh_mult",2.5)))
        form.addRow("Min chunk (ms):", self.sp_min)
        form.addRow("Max silence (ms):", self.sp_sil)
        form.addRow("VAD threshold ×:", self.sp_vad)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _pick_path(self, line: QLineEdit, filter_str: str):
        path,_ = QFileDialog.getSaveFileName(self, "Choose File", "", filter_str)
        if path: line.setText(path)

    def values(self):
        return dict(
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

# ================= 主窗口：英雄卡片 + 大按钮 + 摘要 =================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GuiLiveSubs")
        self.resize(980, 560)
        self.setStyleSheet(STYLE)

        self.data = load_settings()
        self.output_q = queue.Queue()
        self.engine = None

        # 悬浮字幕
        self.overlay = Overlay(self.data.get("max_lines",10),
                               self.data.get("font_size_src",18),
                               self.data.get("font_size_tgt",22))
        self.overlay.set_show_source(self.data.get("show_source",True))

        # 菜单（保留）
        bar = QMenuBar(self); self.setMenuBar(bar)
        m = bar.addMenu("GuiLiveSubs")
        act_prefs = QAction("Preferences…", self); act_prefs.triggered.connect(self.show_prefs); m.addAction(act_prefs)
        m.addSeparator()
        self.act_start = QAction("Start", self); self.act_start.triggered.connect(self.start); m.addAction(self.act_start)
        self.act_stop  = QAction("Stop", self);  self.act_stop.triggered.connect(self.stop);  m.addAction(self.act_stop)
        m.addSeparator()
        act_overlay = QAction("Toggle Overlay", self); act_overlay.triggered.connect(self.toggle_overlay); m.addAction(act_overlay)

        # 快捷键
        QShortcut(QKeySequence("Ctrl+P"), self, activated=self.show_prefs)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.toggle_overlay)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self, activated=self.start)
        QShortcut(QKeySequence("Ctrl+Shift+X"), self, activated=self.stop)

        # —— 中心“英雄卡片”UI ——
        central = QWidget(); root = QVBoxLayout(central)
        root.setContentsMargins(28, 28, 28, 28); root.setSpacing(18)

        hero = QFrame(objectName="HeroCard")
        hero_lay = QVBoxLayout(hero); hero_lay.setContentsMargins(28, 24, 28, 24); hero_lay.setSpacing(16)

        # 阴影
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40); shadow.setOffset(0, 18); shadow.setColor(QColor(0,0,0,140))
        hero.setGraphicsEffect(shadow)

        # 标题与副标题
        title = QLabel("GuiLiveSubs", objectName="Title")
        subtitle = QLabel("Real-time captions and translation. Whisper + DeepL. "
                          "Floating overlay • Word-accurate SRT • Low-latency VAD", objectName="Subtitle")
        subtitle.setWordWrap(True)



        # 大按钮区
        btn_row = QHBoxLayout(); btn_row.setSpacing(12)
        def big_button(text: str, tip: str):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setMinimumHeight(44)
            b.setMinimumWidth(140)
            return b

        self.btn_start = big_button("▶ Start", "Start recognition & translation  (Ctrl+Shift+S)")
        self.btn_stop  = big_button("■ Stop",  "Stop  (Ctrl+Shift+X)")
        self.btn_overlay = big_button("▣ Overlay", "Show/Hide floating captions  (Ctrl+O)")
        self.btn_prefs   = big_button("⚙ Preferences", "Open preferences  (Ctrl+P)")

        self.btn_start.clicked.connect(self.start)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_overlay.clicked.connect(self.toggle_overlay)
        self.btn_prefs.clicked.connect(self.show_prefs)

        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_stop)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_overlay)
        btn_row.addWidget(self.btn_prefs)

        # 摘要信息（当前配置一目了然）
        self.lbl_summary = QLabel(objectName="Summary")
        self.lbl_summary.setWordWrap(True)
        self._refresh_summary_text()

        hero_lay.addWidget(title)
        hero_lay.addWidget(subtitle)
        hero_lay.addLayout(btn_row)
        hero_lay.addWidget(self.lbl_summary)

        root.addWidget(hero)
        self.setCentralWidget(central)

        # 状态栏+队列轮询
        self.txt_writer = None
        self.srt_writer = None
        self.timer = QTimer(self); self.timer.setInterval(50); self.timer.timeout.connect(self._drain); self.timer.start()

        # 初始按钮状态
        self._update_controls(running=False)




    # —— 交互逻辑 ——
    def _update_controls(self, running: bool):
        self.btn_start.setEnabled(not running)
        self.act_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.act_stop.setEnabled(running)

    def _refresh_summary_text(self):
        d = self.data
        parts = [
            f"Target: {d.get('target_lang','zh')}",
            f"Model: {d.get('model_name','base.en')}",
            f"Device: {d.get('device','cpu')}/{d.get('compute_type','int8')}",
            f"Chunk: {d.get('min_chunk_ms',600)}ms · Silence {d.get('max_sil_ms',350)}ms · VAD×{d.get('vad_thresh_mult',2.5)}",
            ("Save: TXT " + d.get('save_txt_path','')) if d.get('save_txt') else "Save: TXT off",
            ("SRT " + d.get('save_srt_path','')) if d.get('save_srt') else "SRT off",
            ("Source line: ON" if d.get('show_source', True) else "Source line: OFF"),
        ]
        self.lbl_summary.setText(" · ".join(parts))

    def show_prefs(self):
        dlg = Prefs(self.data)
        if dlg.exec():
            self.data = save_settings(dlg.values())
            self.overlay.set_show_source(self.data.get("show_source", True))
            self.overlay.set_fonts(self.data.get("font_size_src", 18), self.data.get("font_size_tgt", 22))
            self._refresh_summary_text()
            self.statusBar().showMessage("Preferences saved", 2000)

    def start(self):
        if not self.data.get("deepl_key"):
            QMessageBox.warning(self, "Missing API Key", "请在 Preferences 里填写 DeepL API Key")
            return
        if self.engine:
            return

        # writers
        if self.data.get("save_txt") and self.data.get("save_txt_path"):
            self.txt_writer = TxtWriter(self.data["save_txt_path"]); self.txt_writer.open()
        else:
            self.txt_writer = None
        if self.data.get("save_srt") and self.data.get("save_srt_path"):
            self.srt_writer = SrtWriter(self.data["save_srt_path"], session_start_monotonic=time.monotonic()); self.srt_writer.open()
        else:
            self.srt_writer = None

        # engine
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
        self.overlay.resize_relative(0.75, 0.10)
        self.overlay.show()
        self._update_controls(running=True)
        self.statusBar().showMessage("Running…", 3000)

    def stop(self):
        if self.engine:
            self.engine.stop()
            self.engine = None
        if self.txt_writer:
            self.txt_writer.close(); self.txt_writer = None
        if self.srt_writer:
            self.srt_writer.close(); self.srt_writer = None
        self._update_controls(running=False)
        self.statusBar().showMessage("Stopped.", 2000)

    def toggle_overlay(self):
        if self.overlay.isVisible():
            self.overlay.hide()
        else:
            self.overlay.resize_relative(0.75, 0.10)  # 新增：按 75%×10% 自适应
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
