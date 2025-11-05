# GuiLiveSubs (Windows / macOS)
实时字幕 GUI：Whisper（faster-whisper）+ DeepL，悬浮窗滚动显示（上英下译），可选保存 TXT/SRT。

## 1) install（conda）
```bash
conda env create -f environment.yml
conda activate guisubs
```

or pip：
```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2) run
```bash
python app/main.py
```
 GuiLiveSubs → Preferences… Enter your DeepL API Key, set language and save path; 
 Start → Begin; 
 Toggle Overlay → Show/Hide floating subtitles.

## 3) options
- Device: CPU/auto/cuda（Windows 如需 GPU，请先配好 CUDA 12.x + cuDNN 9，再把 Device 设为 cuda）
- Whisper: base.en（默认），也可以 tiny.en（更快）或 small.en（更准）
- 滚动显示：可调最大行数与字体大小
- 保存：勾选 TXT/SRT 并选择文件路径
