import os
import threading
from pathlib import Path

_load_lock = threading.Lock()

def load_model(path):
    """Load all local assets from ASCII relative paths for Unicode folder support."""
    import sherpa_onnx
    path=Path(path).resolve()
    if not all((path/name).is_file() for name in ('model.int8.onnx','tokens.txt','silero_vad.onnx')):
        raise RuntimeError('模型文件缺失，请保留完整的“应用”文件夹')
    with _load_lock:
        previous=Path.cwd()
        try:
            os.chdir(path)
            recognizer=sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model='model.int8.onnx', tokens='tokens.txt', num_threads=2,
                use_itn=True, language='auto', debug=False, provider='cpu')
            config=sherpa_onnx.VadModelConfig()
            config.silero_vad.model='silero_vad.onnx'
            config.silero_vad.threshold=0.5
            config.silero_vad.min_silence_duration=0.75
            config.silero_vad.min_speech_duration=0.2
            config.silero_vad.max_speech_duration=18
            config.sample_rate=16000
            return recognizer,sherpa_onnx.VoiceActivityDetector(config,buffer_size_in_seconds=60),config.silero_vad.window_size
        finally:
            os.chdir(previous)

def transcribe(recognizer,samples,rate=16000):
    stream=recognizer.create_stream()
    stream.accept_waveform(rate,samples)
    recognizer.decode_stream(stream)
    return stream.result.text.strip()
