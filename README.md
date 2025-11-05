# LiveSubs (Windows / macOS)
Real-time Caption GUI: Whisper (faster-whisper) + DeepL, floating window with scrolling display (English top, translation bottom), optional saving to TXT/SRT.

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
- Device: CPU/auto/cuda (Windows users requiring GPU must first install CUDA 12.x + cuDNN 9, then set Device to cuda)
- Whisper: base.en (default), or tiny.en (faster) or small.en (more accurate)
- Scrolling display: Adjustable maximum lines and font size
- Save: Check TXT/SRT and select file path
