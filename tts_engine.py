"""
TTS Engine — 三層引擎，自動選最佳可用方案

Layer 1 ★ edge-tts streaming + sounddevice + PyAV (FFmpeg)
         → 真正串流：第一個音訊 chunk 到就開始解碼+播放
         → 延遲約 200~350 ms（僅網路 RTT + 伺服器首包時間）

Layer 2   edge-tts + pygame (BytesIO，無暫存檔)
         → 完整下載後播放，BytesIO 省 ~150 ms 磁碟 I/O
         → 延遲約 600~800 ms

Layer 3   Windows SAPI (PowerShell)
         → 品質差，僅最後 fallback
"""

import io
import time
import asyncio
import threading
import subprocess
import numpy as np

# ── 偵測可用套件 ───────────────────────────────────────────────
try:
    import edge_tts as _edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False

try:
    import av as _av
    import sounddevice as _sd
    HAS_STREAMING = True
except ImportError:
    HAS_STREAMING = False

try:
    import pygame as _pygame
    _pygame.mixer.pre_init(44100, -16, 2, 512)   # 小 buffer → 更低啟動延遲
    _pygame.mixer.init()
    HAS_PYGAME = True
except Exception:
    HAS_PYGAME = False

# ── 語音設定 ────────────────────────────────────────────────────
VOICE = 'en-US-JennyNeural'   # 美式自然女聲
# VOICE = 'en-US-GuyNeural'   # 美式自然男聲
# VOICE = 'en-GB-SoniaNeural' # 英式自然女聲
# VOICE = 'en-US-AriaNeural'  # 表情豐富女聲


def engine_name() -> str:
    if HAS_EDGE_TTS:
        if HAS_STREAMING:
            return 'edge-tts 串流 ⚡'
        if HAS_PYGAME:
            return 'edge-tts + pygame'
    return 'Windows SAPI'


# ══════════════════════════════════════════════════════════════════
# _StreamBuffer
# 執行緒安全的阻塞式字節管道：讓 PyAV 能「邊收邊解碼」
# ══════════════════════════════════════════════════════════════════
class _StreamBuffer(io.RawIOBase):
    """
    Producer（下載執行緒）呼叫 feed() 寫入音訊 bytes；
    Consumer（PyAV 解碼器）呼叫 readinto() 讀出，無資料時阻塞等待。
    """

    def __init__(self):
        self._buf  = bytearray()
        self._cond = threading.Condition()
        self._eof  = False

    def feed(self, data: bytes) -> None:
        with self._cond:
            self._buf.extend(data)
            self._cond.notify_all()

    def end(self) -> None:
        with self._cond:
            self._eof = True
            self._cond.notify_all()

    # ── io.RawIOBase 介面 ──────────────────────────────────────
    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray) -> int:
        with self._cond:
            while not self._buf and not self._eof:
                self._cond.wait()
            if not self._buf:      # EOF
                return 0
            n = min(len(b), len(self._buf))
            b[:n] = self._buf[:n]
            del self._buf[:n]
            return n


# ══════════════════════════════════════════════════════════════════
# 公開介面
# ══════════════════════════════════════════════════════════════════
class SpeakSession:
    """管理一次朗讀的完整生命週期（start / stop）"""

    def __init__(self, text: str, on_done, on_error=None):
        self.text     = text
        self.on_done  = on_done
        self.on_error = on_error or (lambda _: None)
        self._stop    = threading.Event()

    def start(self):
        if HAS_EDGE_TTS and HAS_STREAMING:
            target = self._run_streaming       # Layer 1 ★
        elif HAS_EDGE_TTS and HAS_PYGAME:
            target = self._run_buffered        # Layer 2
        else:
            target = self._run_sapi            # Layer 3
        threading.Thread(target=target, daemon=True).start()

    def stop(self):
        self._stop.set()
        if HAS_STREAMING:
            try:
                _sd.stop()
            except Exception:
                pass
        if HAS_PYGAME:
            try:
                _pygame.mixer.music.stop()
            except Exception:
                pass

    # ──────────────────────────────────────────────────────────────
    # Layer 1 ★  串流播放：PyAV 解碼 + sounddevice 即時輸出
    # ──────────────────────────────────────────────────────────────
    def _run_streaming(self):
        raw_buf = _StreamBuffer()
        bio     = io.BufferedReader(raw_buf, buffer_size=8192)

        # 下載執行緒：把 edge-tts 音訊 chunk 餵進 _StreamBuffer
        async def _fetch():
            try:
                comm = _edge_tts.Communicate(self.text, VOICE)
                async for chunk in comm.stream():
                    if chunk['type'] == 'audio':
                        if self._stop.is_set():
                            break
                        raw_buf.feed(chunk['data'])
            finally:
                raw_buf.end()

        fetch_t = threading.Thread(
            target=lambda: asyncio.run(_fetch()), daemon=True)
        fetch_t.start()

        out_stream = None
        try:
            # PyAV 從 bio 讀取並解碼 MP3（阻塞式，配合 _StreamBuffer）
            container = _av.open(bio, format='mp3')
            audio_stream = next(
                s for s in container.streams if s.type == 'audio')

            sample_rate = audio_stream.codec_context.sample_rate
            channels    = audio_stream.codec_context.channels

            out_stream = _sd.OutputStream(
                samplerate=sample_rate,
                channels=channels,
                dtype='float32',
                blocksize=1024,
            )
            out_stream.start()

            resampler = _av.AudioResampler(
                format='fltp',
                layout='stereo' if channels >= 2 else 'mono',
                rate=sample_rate,
            )

            for packet in container.demux(audio_stream):
                if self._stop.is_set():
                    break
                for frame in packet.decode():
                    if self._stop.is_set():
                        break
                    for rf in resampler.resample(frame):
                        data = rf.to_ndarray()          # (channels, samples)
                        data = data.T.astype('float32') # (samples, channels)
                        out_stream.write(data)

        except Exception as e:
            self.on_error(str(e))
        finally:
            if out_stream:
                try:
                    out_stream.stop()
                    out_stream.close()
                except Exception:
                    pass
            fetch_t.join(timeout=5)
            self.on_done()

    # ──────────────────────────────────────────────────────────────
    # Layer 2  BytesIO 緩衝 + pygame（無暫存檔，省磁碟 I/O）
    # ──────────────────────────────────────────────────────────────
    def _run_buffered(self):
        try:
            buf = io.BytesIO()

            async def _collect():
                comm = _edge_tts.Communicate(self.text, VOICE)
                async for chunk in comm.stream():
                    if chunk['type'] == 'audio':
                        buf.write(chunk['data'])

            asyncio.run(_collect())
            buf.seek(0)

            if self._stop.is_set():
                return

            _pygame.mixer.music.load(buf, 'mp3')
            _pygame.mixer.music.play()
            while _pygame.mixer.music.get_busy():
                if self._stop.is_set():
                    _pygame.mixer.music.stop()
                    break
                time.sleep(0.05)
            _pygame.mixer.music.unload()

        except Exception as e:
            self.on_error(str(e))
        finally:
            self.on_done()

    # ──────────────────────────────────────────────────────────────
    # Layer 3  Windows SAPI fallback
    # ──────────────────────────────────────────────────────────────
    def _run_sapi(self):
        try:
            safe = (self.text
                    .replace("'", ' ').replace('"', ' ')
                    .replace('\n', ' ').replace('\r', ''))
            cmd = (
                'Add-Type -AssemblyName System.Speech;'
                '$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;'
                '$s.Rate=0;'
                f"$s.Speak('{safe}')"
            )
            proc = subprocess.Popen(
                ['powershell', '-WindowStyle', 'Hidden', '-Command', cmd],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            while proc.poll() is None:
                if self._stop.is_set():
                    proc.terminate()
                    break
                time.sleep(0.1)
        except Exception as e:
            self.on_error(str(e))
        finally:
            self.on_done()
