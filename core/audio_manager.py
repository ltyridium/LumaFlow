from PySide6.QtCore import QObject, Signal, Slot, QThread, Qt
from PySide6.QtGui import QImage
from dataclasses import dataclass
import numpy as np
from typing import Optional, Dict
import os

from utils.tile_cache import TileCache

try:
    import librosa
    import soundfile as sf
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False


@dataclass
class AudioData:
    """Container for processed audio data"""
    video_path: str
    sample_rate: int
    duration_ms: float
    channel_mode: str  # 'mono', 'stereo', 'left', 'right'

    # Spectrogram data
    spectrogram: np.ndarray  # Shape: (n_mels, time_frames)
    times_ms: np.ndarray     # Time axis in milliseconds
    frequencies: np.ndarray  # Frequency bins in Hz

    # Processing parameters
    n_fft: int = 2048
    hop_length: int = 512
    n_mels: int = 128
    fmin: float = 20.0
    fmax: float = 8000.0


class AudioProcessingWorker(QObject):
    """Background worker for audio extraction and processing"""
    finished = Signal(str, object)  # video_path, AudioData
    error = Signal(str, str)  # video_path, error_message
    progress = Signal(str, str, int)  # video_path, stage_description, percentage

    @Slot(str, str, dict)
    def process_audio(self, video_path: str, channel_mode: str, params: dict):
        """
        Extract audio from video and compute mel-spectrogram

        Args:
            video_path: Path to video file
            channel_mode: 'mono', 'stereo', 'left', 'right'
            params: Processing parameters (n_fft, hop_length, etc.)
        """
        if not LIBROSA_AVAILABLE:
            self.error.emit(video_path, "librosa not installed. Install with: pip install librosa soundfile")
            return

        if not os.path.exists(video_path):
            self.error.emit(video_path, f"Video file not found: {video_path}")
            return

        try:
            import subprocess
            import tempfile
            import shutil

            print(f"[Audio] Processing: {video_path}")
            self.progress.emit(video_path, "开始提取音频", 0)

            # Check if ffmpeg is available
            if shutil.which('ffmpeg') is None:
                print("[Audio] ffmpeg not found, trying direct load...")
                self.progress.emit(video_path, "直接加载音频", 20)
                try:
                    y, sr = librosa.load(video_path, sr=None, mono=False)
                    print(f"[Audio] Direct load successful: {sr}Hz")
                    self.progress.emit(video_path, "音频加载完成", 40)
                except Exception as e:
                    self.error.emit(video_path, f"ffmpeg not found and direct load failed: {str(e)}")
                    return
            else:
                # Use ffmpeg to extract audio
                print("[Audio] Using ffmpeg to extract audio...")
                self.progress.emit(video_path, "使用ffmpeg提取音频", 10)
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_audio:
                    tmp_audio_path = tmp_audio.name

                ffmpeg_cmd = [
                    'ffmpeg', '-i', video_path, '-vn', '-acodec', 'pcm_s16le',
                    '-ar', '44100', '-ac', '2', '-y', tmp_audio_path
                ]

                try:
                    result = subprocess.run(
                        ffmpeg_cmd,
                        check=True,
                        capture_output=True,
                        encoding='utf-8',
                        errors='ignore'
                    )
                    print(f"[Audio] ffmpeg extraction successful")
                    self.progress.emit(video_path, "ffmpeg提取完成", 20)
                    y, sr = librosa.load(tmp_audio_path, sr=None, mono=False)
                    print(f"[Audio] Loaded from temp file: {sr}Hz")
                    self.progress.emit(video_path, "音频加载完成", 40)
                except subprocess.CalledProcessError as e:
                    print(f"[Audio] ffmpeg failed: {e.stderr}")
                    self.error.emit(video_path, f"ffmpeg extraction failed: {e.stderr}")
                    return
                except Exception as e:
                    print(f"[Audio] Load failed: {str(e)}")
                    self.error.emit(video_path, f"Audio load failed: {str(e)}")
                    return
                finally:
                    if os.path.exists(tmp_audio_path):
                        os.remove(tmp_audio_path)

            # Handle channel selection
            if y.ndim == 1:
                # Mono audio
                audio = y
            else:
                # Stereo audio (shape: 2, n_samples)
                if channel_mode == 'left':
                    audio = y[0]
                elif channel_mode == 'right':
                    audio = y[1]
                elif channel_mode == 'mono':
                    audio = librosa.to_mono(y)
                elif channel_mode == 'stereo':
                    # For stereo, use mono for spectrogram but keep stereo info
                    audio = librosa.to_mono(y)
                else:
                    audio = librosa.to_mono(y)

            # Get parameters
            n_fft = params.get('n_fft', 2048)
            hop_length = params.get('hop_length', 512)
            n_mels = params.get('n_mels', 128)
            fmin = params.get('fmin', 20.0)
            fmax = params.get('fmax', 8000.0)

            # Compute mel-spectrogram
            self.progress.emit(video_path, "计算频谱图", 60)
            mel_spec = librosa.feature.melspectrogram(
                y=audio,
                sr=sr,
                n_fft=n_fft,
                hop_length=hop_length,
                n_mels=n_mels,
                fmin=fmin,
                fmax=fmax
            )

            # Convert to dB scale
            self.progress.emit(video_path, "应用归一化", 80)
            mel_spec_db = librosa.power_to_db(mel_spec, ref=np.max)

            # Compute time axis in milliseconds
            times = librosa.frames_to_time(
                np.arange(mel_spec_db.shape[1]),
                sr=sr,
                hop_length=hop_length
            )
            times_ms = times * 1000.0

            # Compute frequency bins
            frequencies = librosa.mel_frequencies(n_mels=n_mels, fmin=fmin, fmax=fmax)

            # Calculate duration
            duration_ms = len(audio) / sr * 1000.0

            # Create AudioData object
            self.progress.emit(video_path, "处理完成", 100)
            audio_data = AudioData(
                video_path=video_path,
                sample_rate=sr,
                duration_ms=duration_ms,
                channel_mode=channel_mode,
                spectrogram=mel_spec_db.astype(np.float32),
                times_ms=times_ms.astype(np.float32),
                frequencies=frequencies.astype(np.float32),
                n_fft=n_fft,
                hop_length=hop_length,
                n_mels=n_mels,
                fmin=fmin,
                fmax=fmax
            )

            self.finished.emit(video_path, audio_data)

        except Exception as e:
            self.error.emit(video_path, f"Audio processing failed: {str(e)}")


class AudioManager(QObject):
    """Manages audio extraction, caching, and tile rendering for video files"""
    audio_processed = Signal(str, object)  # video_path, AudioData
    processing_failed = Signal(str, str)  # video_path, error_message
    audio_progress = Signal(str, str, int)  # video_path, stage, percentage
    request_processing = Signal(str, str, dict)  # 用于触发后台处理

    # 瓦片渲染信号
    tile_ready = Signal(str, object)  # cache_key, QImage
    request_tile = Signal(object, str, float, float, str, float)  # audio_data, cache_key, start_ms, end_ms, colormap, request_time

    def __init__(self):
        super().__init__()
        self.audio_cache: Dict[str, AudioData] = {}

        # 瓦片缓存
        self.tile_cache = TileCache(max_size=200)

        # Setup audio processing worker thread
        self.processing_thread = QThread()
        self.worker = AudioProcessingWorker()
        self.worker.moveToThread(self.processing_thread)

        # Connect signals - 使用 QueuedConnection 确保在工作线程执行
        self.request_processing.connect(self.worker.process_audio, Qt.QueuedConnection)
        self.worker.finished.connect(self._on_processing_finished)
        self.worker.error.connect(self._on_processing_error)
        self.worker.progress.connect(self.audio_progress)

        # Start audio processing thread
        self.processing_thread.start()

        # Setup texture rendering worker thread
        self.texture_thread = QThread()
        from ui.audio_texture_worker import AudioTextureWorker
        self.texture_worker = AudioTextureWorker()
        self.texture_worker.moveToThread(self.texture_thread)

        # Connect texture rendering signals
        self.request_tile.connect(self.texture_worker.render_tile, Qt.QueuedConnection)
        self.texture_worker.texture_ready.connect(self._on_tile_ready)

        # Start texture rendering thread
        self.texture_thread.start()

        # Default processing parameters - 增大 hop_length 减少数据量
        self.default_params = {
            'n_fft': 2048,
            'hop_length': 1024,  # 从 512 增加到 1024，减少一半数据点
            'n_mels': 128,
            'fmin': 20.0,
            'fmax': 8000.0
        }

    def extract_audio(self, video_path: str, channel_mode: str = 'mono'):
        """
        Request audio extraction from video file

        Args:
            video_path: Path to video file
            channel_mode: 'mono', 'stereo', 'left', 'right'
        """
        if not LIBROSA_AVAILABLE:
            self.processing_failed.emit(video_path, "librosa not installed")
            return

        # Check cache
        cache_key = f"{video_path}_{channel_mode}"
        if cache_key in self.audio_cache:
            # Return cached data
            self.audio_processed.emit(video_path, self.audio_cache[cache_key])
            return

        # Process in background thread - 通过信号触发，确保在工作线程执行
        self.request_processing.emit(video_path, channel_mode, self.default_params)

    def update_params(self, params: dict):
        """Update default processing parameters"""
        self.default_params.update(params)

    def get_audio_data(self, video_path: str, channel_mode: str = 'mono') -> Optional[AudioData]:
        """
        Retrieve cached audio data

        Args:
            video_path: Path to video file
            channel_mode: Channel mode used for processing

        Returns:
            AudioData if cached, None otherwise
        """
        cache_key = f"{video_path}_{channel_mode}"
        return self.audio_cache.get(cache_key)

    def clear_cache(self, video_path: str = None):
        """
        Clear audio cache

        Args:
            video_path: If provided, clear only this video's cache. Otherwise clear all.
        """
        # 先清空瓦片缓存
        self.tile_cache.clear()

        # 再清空音频数据缓存
        if video_path:
            # Clear all entries for this video path
            keys_to_remove = [k for k in self.audio_cache.keys() if k.startswith(video_path)]
            for key in keys_to_remove:
                del self.audio_cache[key]
        else:
            self.audio_cache.clear()

    @Slot(str, object)
    def _on_processing_finished(self, video_path: str, audio_data: AudioData):
        """Handle successful audio processing"""
        # Cache the result
        cache_key = f"{video_path}_{audio_data.channel_mode}"
        self.audio_cache[cache_key] = audio_data

        # Emit signal
        self.audio_processed.emit(video_path, audio_data)

    @Slot(str, str)
    def _on_processing_error(self, video_path: str, error_message: str):
        """Handle audio processing error"""
        self.processing_failed.emit(video_path, error_message)

    @Slot(str, object)
    def _on_tile_ready(self, cache_key: str, image: QImage):
        """Handle tile rendering completion"""
        self.tile_ready.emit(cache_key, image)

    def shutdown(self):
        """Cleanup threads properly"""
        try:
            # Stop audio processing thread
            if hasattr(self, 'processing_thread') and self.processing_thread.isRunning():
                self.processing_thread.quit()
                if not self.processing_thread.wait(3000):
                    self.processing_thread.terminate()
                    self.processing_thread.wait()

            # Stop texture rendering thread
            if hasattr(self, 'texture_thread') and self.texture_thread.isRunning():
                self.texture_thread.quit()
                if not self.texture_thread.wait(3000):
                    self.texture_thread.terminate()
                    self.texture_thread.wait()
        except RuntimeError:
            pass  # Qt objects already deleted

    def __del__(self):
        """Cleanup threads on deletion"""
        try:
            self.shutdown()
        except (RuntimeError, AttributeError):
            pass  # Qt objects already deleted
