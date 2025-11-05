import time, queue, threading, numpy as np
import sounddevice as sd
import requests
from faster_whisper import WhisperModel

class EnergyVadChunker:
    def __init__(self, sr=16000, frame_ms=20, min_chunk_ms=600, max_sil_ms=350, thresh_mult=2.5):
        self.sr = sr
        self.frame_ms = frame_ms
        self.frame_len = sr * frame_ms // 1000
        self.min_frames = max(1, min_chunk_ms // frame_ms)
        self.max_sil_frames = max(1, max_sil_ms // frame_ms)
        self.thresh_mult = thresh_mult
        self.calibrating_frames = max(1, int(1000 / frame_ms))  # ~1s
        self.reset()

    def reset(self):
        self.frames = []
        self.voiced = 0
        self.sil = 0
        self.energy_thresh = None
        self._calib = []

    @staticmethod
    def _rms(f32: np.ndarray) -> float:
        return float(np.sqrt(np.mean(np.square(f32), dtype=np.float32)))

    def _is_voiced(self, f32: np.ndarray) -> bool:
        e = self._rms(f32)
        if self.energy_thresh is None:
            self._calib.append(e)
            if len(self._calib) >= self.calibrating_frames:
                base = np.median(np.asarray(self._calib, dtype=np.float32))
                self.energy_thresh = max(1e-4, float(base) * self.thresh_mult)
            return False
        return e > self.energy_thresh

    def process(self, pcm16: bytes):
        f32 = (np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0)
        voiced = self._is_voiced(f32)
        self.frames.append(pcm16)
        if voiced:
            self.voiced += 1
            self.sil = 0
        else:
            self.sil += 1
        if self.energy_thresh is None:
            return None
        if self.voiced >= self.min_frames and self.sil >= self.max_sil_frames:
            data = b"".join(self.frames)
            self.reset()
            return data
        if len(self.frames) > int(30000 / self.frame_ms):
            data = b"".join(self.frames)
            self.reset()
            return data
        return None

def _norm_lang(code: str, *, for_target: bool = True) -> str:
    if not code:
        return "ZH" if for_target else "EN"
    c = code.strip().upper()
    # 常见别名归一
    aliases = {
        "CN": "ZH", "ZH-CN": "ZH", "ZH-HANS": "ZH", "ZH-HANT": "ZH",
        "EN": "EN-US"  # DeepL 目标语言不接受裸 EN，给个更常见的缺省
    }
    return aliases.get(c, c)


class DeepLClient:
    def __init__(self, auth_key: str, api_base: str = "https://api.deepl.com",
                 target_lang: str = "ZH", source_lang: str = "EN"):
        self.key = auth_key
        self.base = api_base.rstrip("/")
        self.lang = _norm_lang(target_lang, for_target=True)
        self.src  = _norm_lang(source_lang, for_target=False)

    def translate(self, text: str) -> str:
        try:
            data = {
                "auth_key": self.key,
                "text": text,
                "target_lang": self.lang,
                "source_lang": self.src,
                "split_sentences": "0",
                "preserve_formatting": "1"
            }
            r = requests.post(f"{self.base}/v2/translate", data=data, timeout=15)
            r.raise_for_status()
            js = r.json()
            return js["translations"][0]["text"]
        except Exception as e:
            return f"[DeepL error] {e}"

class AsrEngine(threading.Thread):
    """
    Runs mic capture + VAD chunking + Whisper + DeepL.
    Pushes dict items into output_q:
      {"src": str, "tgt": str, "start": float, "end": float}
    start/end are session-relative monotonic seconds.
    """
    def __init__(self, output_q: "queue.Queue", deepl_key: str, target_lang: str,
                 model_name="base.en", device="cpu", compute_type="int8",
                 min_chunk_ms=600, max_sil_ms=350, vad_thresh_mult=2.5,
                 api_base="https://api.deepl.com"):
        super().__init__(daemon=True)
        self.output_q = output_q
        self.sr = 16000
        self.frame_ms = 20
        self.frame_len = self.sr * self.frame_ms // 1000
        self.vad = EnergyVadChunker(self.sr, self.frame_ms, min_chunk_ms, max_sil_ms, vad_thresh_mult)
        self._stop = threading.Event()
        self.q = queue.Queue(maxsize=4000)
        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)
        # warm up
        list(self.model.transcribe(np.zeros(self.sr, dtype=np.float32), beam_size=1, language="en"))
        self.translator = DeepLClient(
            deepl_key, api_base=api_base,
            target_lang=target_lang,
            source_lang="EN"
        )
        self.session_start = time.monotonic()

    def stop(self):
        self._stop.set()

    def _audio_cb(self, indata, frames, time_info, status):
        pcm16 = (np.clip(indata[:,0], -1.0, 1.0) * 32768.0).astype(np.int16).tobytes()
        self.q.put(pcm16)

    def _audio_loop(self):
        with sd.InputStream(samplerate=self.sr, channels=1, dtype="float32",
                            callback=self._audio_cb, blocksize=self.frame_len):
            bsize = self.frame_len * 2
            buf = b""
            while not self._stop.is_set():
                try:
                    blk = self.q.get(timeout=0.3)
                except queue.Empty:
                    continue
                buf += blk
                while len(buf) >= bsize:
                    f = buf[:bsize]
                    buf = buf[bsize:]
                    done = self.vad.process(f)
                    if done:
                        dur = len(done) / 2 / self.sr
                        end_mono = time.monotonic()
                        start_mono = end_mono - dur
                        self._handle_chunk(done, start_mono, end_mono)

    def _handle_chunk(self, pcm16: bytes, start_mono: float, end_mono: float):
        """
        将一个 VAD 切出来的 chunk 做成多条“词组/小句”字幕：
        - 如果有 word_timestamps，就按词的时间做分组，并精确到每组的起止时间
        - 没有的话，退化为按 segment 的起止时间
        每条小句都会单独送 DeepL 翻译，并进入 UI/SRT。
        """
        import math

        audio = (np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0)
        segments, info = self.model.transcribe(
            audio, language="en", beam_size=1, vad_filter=False,
            condition_on_previous_text=False, word_timestamps=True
        )

        # 分组阈值：同一小句最多多少词、相邻词间最大间隔（秒）、句末标点断句
        MAX_WORDS = 8
        MAX_GAP_S = 0.5
        PUNC_BREAKS = {".", "!", "?", ",", ";", ":", "。", "！", "？", "，", "；", "："}

        def flush_group(group):
            if not group:
                return
            # 组文本与时间（相对 chunk 开头），再换算成绝对单调时钟
            text = "".join(w.word for w in group).strip()
            text = " ".join(text.split())  # 规整空格
            gstart = group[0].start or 0.0
            gend = group[-1].end or gstart
            abs_start = start_mono + float(gstart)
            abs_end = start_mono + float(gend)

            if text:
                tgt = self.translator.translate(text)
                self.output_q.put({
                    "src": text,
                    "tgt": tgt,
                    "start": abs_start,
                    "end": abs_end
                })
            group.clear()

        used_word_level = False
        for s in segments:
            words = getattr(s, "words", None) or []
            if words:
                used_word_level = True
                group = []
                prev_end = None
                for w in words:
                    token = (w.word or "").strip()
                    gap_ok = (prev_end is None) or ((w.start or 0.0) - prev_end <= MAX_GAP_S)
                    group.append(w)
                    # 断句条件：到上限、遇到句末标点、词间隔太大
                    end_with_punc = token in PUNC_BREAKS or (token and token[-1] in PUNC_BREAKS)
                    reach_limit = len(group) >= MAX_WORDS
                    gap_break = (prev_end is not None) and ((w.start or 0.0) - prev_end > MAX_GAP_S)
                    if end_with_punc or reach_limit or gap_break:
                        flush_group(group)
                    prev_end = w.end or w.start or prev_end
                # 收尾
                flush_group(group)

        # 如果模型/包不返回逐词时间，则退化到按 segment 输出（仍使用准确的 segment 起止）
        if not used_word_level:
            merged = []
            for s in segments:
                txt = (s.text or "").strip()
                if not txt:
                    continue
                seg_start = float(getattr(s, "start", 0.0) or 0.0)
                seg_end = float(getattr(s, "end", seg_start))
                abs_start = start_mono + seg_start
                abs_end = start_mono + seg_end
                merged.append((txt, abs_start, abs_end))

            # 若所有 segment 很短，也可以合并输出；这里直接逐段发送：
            for txt, abs_start, abs_end in merged:
                tgt = self.translator.translate(txt)
                self.output_q.put({
                    "src": txt,
                    "tgt": tgt,
                    "start": abs_start,
                    "end": abs_end
                })

    def run(self):
        t = threading.Thread(target=self._audio_loop, daemon=True)
        t.start()
        while not self._stop.is_set():
            time.sleep(0.1)
