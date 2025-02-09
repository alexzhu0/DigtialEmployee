import edge_tts
import asyncio
import json
import websockets
import base64
import hmac
import datetime
import hashlib
import uuid
from urllib.parse import urlparse
import time
from config.config import settings

class TTSEngine:
    def __init__(self):
        self.voice = settings.TTS_VOICE
        self.rate = settings.TTS_RATE
        self.volume = settings.TTS_VOLUME

    async def text_to_speech(self, text: str, output_path: str):
        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate, volume=self.volume)
        await communicate.save(output_path)

class XunfeiASR:
    def __init__(self):
        self.app_id = settings.XUNFEI_APPID
        self.api_key = settings.XUNFEI_APIKEY
        self.api_secret = settings.XUNFEI_APISECRET
        self.host = "ws://rtasr.xfyun.cn/v1/ws"

    def create_url(self):
        """生成鉴权url"""
        url = urlparse(self.host)
        date = datetime.datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT')
        signature_origin = f"host: {url.netloc}\ndate: {date}\nGET {url.path} HTTP/1.1"
        signature_sha = hmac.new(self.api_secret.encode('utf-8'),
                               signature_origin.encode('utf-8'),
                               digestmod=hashlib.sha256).digest()
        signature_sha_base64 = base64.b64encode(signature_sha).decode(encoding='utf-8')
        authorization_origin = f'api_key="{self.api_key}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature_sha_base64}"'
        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')
        
        v = {
            "authorization": authorization,
            "date": date,
            "host": url.netloc
        }
        url = f"wss://{url.netloc}{url.path}?{urllib.parse.urlencode(v)}"
        return url

    async def process_audio(self, audio_data: bytes, callback):
        """处理音频数据"""
        url = self.create_url()
        
        async with websockets.connect(url) as ws:
            await ws.send(json.dumps({
                "common": {"app_id": self.app_id},
                "business": {
                    "language": "zh_cn",
                    "domain": "iat",
                    "accent": "mandarin"
                },
                "data": {
                    "status": 0,
                    "format": "audio/L16;rate=16000",
                    "encoding": "raw"
                }
            }))
            
            # 发送音频数据
            chunk_size = 1280
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i + chunk_size]
                await ws.send(json.dumps({
                    "data": {
                        "status": 1 if i + chunk_size < len(audio_data) else 2,
                        "audio": base64.b64encode(chunk).decode(),
                        "format": "audio/L16;rate=16000",
                        "encoding": "raw"
                    }
                }))
                
            # 接收识别结果
            while True:
                result = await ws.recv()
                result_dict = json.loads(result)
                
                if result_dict["data"]["status"] == 2:
                    text = result_dict["data"]["result"]["text"]
                    await callback(text)
                    break

class AudioProcessor:
    def __init__(self):
        self.tts_engine = TTSEngine()
        self.asr_engine = XunfeiASR()
    
    async def synthesize_speech(self, text: str, output_path: str):
        """文本转语音"""
        await self.tts_engine.text_to_speech(text, output_path)
    
    async def recognize_speech(self, audio_data: bytes, callback):
        """语音识别"""
        await self.asr_engine.process_audio(audio_data, callback) 