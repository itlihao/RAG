# coding=utf-8
#
# Installation instructions for pyaudio:
# APPLE Mac OS X
#   brew install portaudio
#   pip install pyaudio
# Debian/Ubuntu
#   sudo apt-get install python-pyaudio python3-pyaudio
#   or
#   pip install pyaudio
# CentOS
#   sudo yum install -y portaudio portaudio-devel && pip install pyaudio
# Microsoft Windows
#   python -m pip install pyaudio

# 通义千问tts
import os
import dashscope
import pyaudio
import time
import base64
import numpy as np

p = pyaudio.PyAudio()
# 创建音频流
stream = p.open(format=pyaudio.paInt16,
                channels=1,
                rate=24000,
                output=True)


text = "大漠孤烟直，长河落日圆"
responses = dashscope.audio.qwen_tts.SpeechSynthesizer.call(
    model="qwen-tts",
    api_key=os.getenv("MODEL_API_KEY"),
    text=text,
    voice="Chelsie",
    stream=True
)
for chunk in responses:
    audio_string = chunk["output"]["audio"]["data"]
    wav_bytes = base64.b64decode(audio_string)
    audio_np = np.frombuffer(wav_bytes, dtype=np.int16)
    # 直接播放音频数据
    stream.write(audio_np.tobytes())

time.sleep(0.8)
# 清理资源
stream.stop_stream()
stream.close()
p.terminate()