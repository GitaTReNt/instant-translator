# GuiLiveSubs (Windows / macOS)
实时字幕 GUI：Whisper（faster-whisper）+ DeepL，悬浮窗滚动显示（上英下译），可选保存 TXT/SRT。

## 1) 安装（conda 推荐）
```bash
conda env create -f environment.yml
conda activate guisubs
```

或 pip：
```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2) 运行
```bash
python app/main.py
```
首次启动后，菜单 `GuiLiveSubs → Preferences…` 填写 DeepL API Key，设置语言与保存路径；`Start` 开始；`Toggle Overlay` 显示/隐藏悬浮字幕。

## 3) 选项
- Device: CPU/auto/cuda（Windows 如需 GPU，请先配好 CUDA 12.x + cuDNN 9，再把 Device 设为 cuda）
- Whisper: base.en（默认），也可以 tiny.en（更快）或 small.en（更准）
- 滚动显示：可调最大行数与字体大小
- 保存：勾选 TXT/SRT 并选择文件路径
