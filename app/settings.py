import json, os, platform

APP_NAME = "GuiLiveSubs"

def app_support_dir() -> str:
    sys = platform.system()
    if sys == "Darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif sys == "Windows":
        base = os.getenv("APPDATA", os.path.expanduser("~"))
    else:
        base = os.getenv("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d

SETTINGS_PATH = os.path.join(app_support_dir(), "settings.json")

DEFAULTS = {
    "deepl_key": "",
    "target_lang": "ZH",
    "show_source": True,
    "model_name": "base.en",
    "device": "cpu",
    "compute_type": "int8",
    "min_chunk_ms": 600,
    "max_sil_ms": 350,
    "vad_thresh_mult": 2.5,
    "max_lines": 10,
    "font_size_src": 18,
    "font_size_tgt": 22,
    "save_txt": False,
    "save_txt_path": "",
    "save_srt": False,
    "save_srt_path": ""
}

def load_settings():
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    out = DEFAULTS.copy()
    out.update(data)
    return out

def save_settings(d: dict):
    data = DEFAULTS.copy()
    data.update(d or {})
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data
