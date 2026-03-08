#!/usr/bin/env python3
"""
Nexta Live OSINT Pipeline v2.0
Arhitectură: Async + CQRS + Circuit Breaker
"""

import os
import asyncio
import hashlib
import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Set
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

import aiohttp
import requests
from PIL import Image
import pytesseract
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Message
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Optional Sentry
try:
    import sentry_sdk
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False

# ==========================================
# CONFIGURARE & SECRETE
# ==========================================
@dataclass(frozen=True)
class Config:
    API_ID: int = field(default_factory=lambda: int(os.getenv('NEXTA_API_ID') or os.getenv('API_ID', 0)))
    API_HASH: str = field(default_factory=lambda: os.getenv('NEXTA_API_HASH') or os.getenv('API_HASH', ''))
    SESSION_STRING: str = field(default_factory=lambda: os.getenv('NEXTA_SESSION') or os.getenv('TELEGRAM_SESSION', ''))
    DEST_CHANNEL: str = field(default_factory=lambda: os.getenv('NEXTA_DEST_ID') or os.getenv('NEXTALIVEROMANIA_ID', ''))
    DEEPSEEK_KEY: str = field(default_factory=lambda: os.getenv('DEEPSEEK_KEY') or os.getenv('DEEPSEEK_API_KEY', ''))
    DRY_RUN: bool = field(default_factory=lambda: (os.getenv('DRY_RUN') or 'false').lower() == 'true')
    MAX_FILE_SIZE_MB: int = 50
    SIMILARITY_THRESHOLD: float = 0.85
    MAX_WORKERS: int = 4
    
    def validate(self) -> None:
        required = {
            'API_ID': self.API_ID,
            'API_HASH': self.API_HASH,
            'SESSION_STRING': self.SESSION_STRING,
            'DEST_CHANNEL': self.DEST_CHANNEL
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Configurare incompletă - lipsesc: {', '.join(missing)}")

# ==========================================
# MODELE DE DATE
# ==========================================
class ContentType(Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"

@dataclass
class RawContent:
    source_channel: str
    message_id: int
    content_type: ContentType
    text: str = ""
    media_path: Optional[str] = None
    ocr_text: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict = field(default_factory=dict)

@dataclass
class ProcessedContent:
    raw: RawContent
    translated_text: str
    quality_score: float
    hash_id: str
    processing_time_ms: int = 0

# ==========================================
# CIRCUIT BREAKER
# ==========================================
class CircuitBreaker:
    def __init__(self, failure_threshold=3, timeout=60):
        self.failures = 0
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.last_failure_time = None
        self.state = "CLOSED"
    
    def call(self, func):
        async def wrapper(*args, **kwargs):
            if self.state == "OPEN":
                if self.last_failure_time and datetime.now() - self.last_failure_time < timedelta(seconds=self.timeout):
                    raise Exception("Circuit breaker is OPEN - API unavailable")
                self.state = "HALF_OPEN"
            
            try:
                result = await func(*args, **kwargs)
                if self.state == "HALF_OPEN":
                    self.state = "CLOSED"
                    self.failures = 0
                return result
            except Exception as e:
                self.failures += 1
                self.last_failure_time = datetime.now()
                if self.failures >= self.failure_threshold:
                    self.state = "OPEN"
                raise e
        return wrapper

# ==========================================
# SERVICII
# ==========================================
class OCRService:
    def __init__(self, max_workers=4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.supported_langs = ['eng', 'rus', 'heb', 'ron', 'ukr']
    
    async def extract(self, image_path: str) -> str:
        if not os.path.exists(image_path):
            return ""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self._sync_extract, image_path)
    
    def _sync_extract(self, path: str) -> str:
        try:
            img = Image.open(path)
            if img.mode != 'L':
                img = img.convert('L')
            width, height = img.size
            if width > 2000 or height > 2000:
                img.thumbnail((2000, 2000))
            
            config = '--psm 6'
            text = pytesseract.image_to_string(
                img, 
                lang='+'.join(self.supported_langs),
                config=config
            )
            return text.strip()
        except Exception as e:
            logging.error(f"OCR failed for {path}: {e}")
            return ""

class DeepSeekService:
    def __init__(self, api_key: str, circuit_breaker: CircuitBreaker):
        self.api_key = api_key
        self.cb = circuit_breaker
        self.cache: Dict[str, str] = {}
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    @CircuitBreaker.call
    async def translate_and_adapt(self, text: str, ocr_context: str = "") -> tuple[str, float]:
        if not text or len(text.strip()) < 5:
            return "", 0.0
        
        cache_key = hashlib.md5(f"{text[:500]}{ocr_context[:200]}".encode()).hexdigest()[:16]
        if cache_key in self.cache:
            return self.cache[cache_key], 1.0
        
        prompt = self._build_prompt(text, ocr_context)
        
        try:
            async with self.session.post(
                "https://api.deepseek.com/v1/chat/completions",
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 1500
                }
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"DeepSeek API error {resp.status}: {error_text}")
                
                data = await resp.json()
                result = data['choices'][0]['message']['content'].strip()
                quality = self._calculate_quality(result, text)
                self.cache[cache_key] = result
                return result, quality
                
        except Exception as e:
            logging.error(f"DeepSeek error: {e}")
            raise
    
    def _build_prompt(self, text: str, ocr: str) -> str:
        return f"""Ești jurnalist OSINT senior. Procesează următoarea informație:

SURSA: {text[:1200]}
CONTEXT IMAGINE (OCR): {ocr[:300] if ocr else 'N/A'}

INSTRUCȚIUNI STRICTE:
1. Traduce în română impecabilă (stil Reuters/BBC)
2. Structurează: Titlu scurt + Corp informativ + Context (dacă necesar)
3. ELIMINĂ: link-uri, @mențiuni, emoji-uri inutile, propaganda evidentă
4. ADAPTEAZĂ: Converteste unități imperiale în metrice, orele în TZ București (EET/EEST)
5. VERIFICĂ: Dacă informația pare falsă, adaugă [NECONFIRMAT]

RĂSPUNS: DOAR ȘTIREA PROCESATĂ, fără meta-comentarii."""

    def _calculate_quality(self, output: str, input_text: str) -> float:
        if not output or len(output) < 20:
            return 0.0
        ratio = len(output) / max(len(input_text), 1)
        if ratio < 0.05:
            return 0.3
        if ratio > 2.0:
            return 0.7
        score = 0.9
        if "[NECONFIRMAT]" in output:
            score -= 0.1
        if len(output.split('.')) < 2:
            score -= 0.2
        return max(0.0, score)

class DeduplicationService:
    def __init__(self, threshold: float = 0.85):
        self.threshold = threshold
        self.vectorizer = TfidfVectorizer(max_features=1000, stop_words='english', min_df=1)
        self.seen_hashes: Set[str] = set()
        self.corpus: List[str] = []
        self.lock = asyncio.Lock()
    
    async def is_duplicate(self, text: str) -> bool:
        if not text:
            return False
        
        async with self.lock:
            text_hash = hashlib.sha256(text[:200].encode()).hexdigest()[:32]
            if text_hash in self.seen_hashes:
                return True
            
            if len(self.corpus) > 0 and len(text) > 20:
                try:
                    all_texts = self.corpus[-50:] + [text]
                    vectors = self.vectorizer.fit_transform(all_texts)
                    similarity = cosine_similarity(vectors[-1:], vectors[:-1])
                    if similarity.max() > self.threshold:
                        logging.info(f"Fuzzy duplicate detected (sim: {similarity.max():.2f})")
                        return True
                except Exception as e:
                    logging.debug(f"Similarity calc failed: {e}")
            
            self.seen_hashes.add(text_hash)
            self.corpus.append(text)
            if len(self.corpus) > 200:
                self.corpus.pop(0)
            return False

class MetricsCollector:
    def __init__(self):
        self.data = {
            "start_time": datetime.now().isoformat(),
            "sources_processed": {},
            "api_calls": 0,
            "api_cost_estimate_usd": 0.0,
            "posts_created": 0,
            "errors": [],
            "processing_times_ms": []
        }
        self.lock = asyncio.Lock()
    
    async def record_api_call(self, tokens: int = 800):
        async with self.lock:
            self.data["api_calls"] += 1
            self.data["api_cost_estimate_usd"] += (tokens / 1000) * 0.0015
    
    async def record_post(self, source: str, quality: float, proc_time: int = 0):
        async with self.lock:
            self.data["posts_created"] += 1
            if proc_time > 0:
                self.data["processing_times_ms"].append(proc_time)
            if source not in self.data["sources_processed"]:
                self.data["sources_processed"][source] = {"count": 0, "avg_quality": 0.0}
            src = self.data["sources_processed"][source]
            src["count"] += 1
            src["avg_quality"] = (src["avg_quality"] * (src["count"]-1) + quality) / src["count"]
    
    async def record_error(self, source: str, error: str):
        async with self.lock:
            self.data["errors"].append({
                "source": source,
                "error": error[:200],
                "time": datetime.now().isoformat()
            })
    
    def save(self):
        self.data["end_time"] = datetime.now().isoformat()
        if self.data["processing_times_ms"]:
            self.data["avg_processing_time_ms"] = np.mean(self.data["processing_times_ms"])
        
        Path("logs").mkdir(exist_ok=True)
        with open("logs/metrics.json", "w", encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        logging.info(f"💾 Metrics saved. Posts: {self.data['posts_created']}, Cost: ${self.data['api_cost_estimate_usd']:.4f}")

# ==========================================
# PIPELINE PRINCIPAL
# ==========================================
class NextaPipeline:
    CANALE_SURSA = ['nexta_live', 'TheStudyofWar', 'osintdefender', 'mossad_telegram']
    SEMNATURA = '@real_live_by_luci'
    
    def __init__(self, config: Config):
        self.config = config
        self.ocr = OCRService(max_workers=config.MAX_WORKERS)
        self.dedup = DeduplicationService(threshold=config.SIMILARITY_THRESHOLD)
        self.metrics = MetricsCollector()
        self.circuit = CircuitBreaker()
        self.deepseek: Optional[DeepSeekService] = None
        self.client: Optional[TelegramClient] = None
    
    async def __aenter__(self):
        self.client = TelegramClient(
            StringSession(self.config.SESSION_STRING),
            self.config.API_ID,
            self.config.API_HASH
        )
        await self.client.connect()
        if not await self.client.is_user_authorized():
            raise Exception("Telegram client not authorized - check session string")
        
        self.deepseek = DeepSeekService(self.config.DEEPSEEK_KEY, self.circuit)
        await self.deepseek.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.deepseek:
            await self.deepseek.__aexit__(exc_type, exc_val, exc_tb)
        if self.client:
            await self.client.disconnect()
        self.metrics.save()
    
    async def fetch_history(self, limit: int = 50) -> List[str]:
        try:
            entity = await self.client.get_entity(self.config.DEST_CHANNEL)
            messages = await self.client.get_messages(entity, limit=limit)
            return [m.text[:300] for m in messages if m.text]
        except Exception as e:
            logging.error(f"Failed to fetch history: {e}")
            return []
    
    async def process_message(self, msg: Message, source: str) -> Optional[ProcessedContent]:
        start_time = datetime.now()
        try:
            raw = await self._extract_raw_content(msg, source)
            combined = f"{raw.text} {raw.ocr_text}".strip()
            
            if not combined:
                return None
            
            if await self.dedup.is_duplicate(combined):
                logging.debug(f"Duplicate skipped from {source}")
                return None
            
            translated, quality = await self.deepseek.translate_and_adapt(
                raw.text, raw.ocr_text
            )
            await self.metrics.record_api_call()
            
            if quality < 0.5:
                logging.warning(f"Low quality ({quality:.2f}) from {source}, skipping")
                if raw.media_path and os.path.exists(raw.media_path):
                    os.remove(raw.media_path)
                return None
            
            content_hash = hashlib.sha256(
                f"{source}:{msg.id}:{translated[:100]}".encode()
            ).hexdigest()[:16]
            
            proc_time = int((datetime.now() - start_time).total_seconds() * 1000)
            return ProcessedContent(
                raw=raw,
                translated_text=translated,
                quality_score=quality,
                hash_id=content_hash,
                processing_time_ms=proc_time
            )
            
        except Exception as e:
            await self.metrics.record_error(source, str(e))
            logging.error(f"Processing error for {source}/{msg.id}: {e}")
            return None
    
    async def _extract_raw_content(self, msg: Message, source: str) -> RawContent:
        media_path = None
        ocr_text = ""
        
        if msg.media:
            try:
                if hasattr(msg.media, 'size') and msg.media.size:
                    size_mb = msg.media.size / 1024 / 1024
                    if size_mb > self.config.MAX_FILE_SIZE_MB:
                        logging.warning(f"File too large: {size_mb:.1f}MB from {source}")
                        return RawContent(source, msg.id, ContentType.TEXT, msg.text or "")
                
                media_path = await msg.download_media(file="temp/")
                
                if msg.photo and media_path and os.path.exists(media_path):
                    ocr_text = await self.ocr.extract(media_path)
            except Exception as e:
                logging.error(f"Media download failed: {e}")
        
        content_type = ContentType.IMAGE if msg.photo else \
                      ContentType.VIDEO if msg.video else \
                      ContentType.DOCUMENT if msg.document else ContentType.TEXT
        
        return RawContent(
            source_channel=source,
            message_id=msg.id,
            content_type=content_type,
            text=msg.text or "",
            media_path=media_path,
            ocr_text=ocr_text
        )
    
    async def publish(self, content: ProcessedContent) -> bool:
        if self.config.DRY_RUN:
            logging.info(f"[DRY RUN] Would post from {content.raw.source_channel}: {content.translated_text[:80]}...")
            await self.metrics.record_post(content.raw.source_channel, content.quality_score, content.processing_time_ms)
            return True
        
        caption = f"{content.translated_text}\n\n{self.SEMNATURA}\n🔍 ID: {content.hash_id}"
        
        try:
            entity = await self.client.get_entity(self.config.DEST_CHANNEL)
            
            if content.raw.media_path and os.path.exists(content.raw.media_path):
                await self.client.send_file(
                    entity,
                    content.raw.media_path,
                    caption=caption,
                    supports_streaming=True
                )
                try:
                    os.remove(content.raw.media_path)
                except:
                    pass
            else:
                await self.client.send_message(entity, caption)
            
            await self.metrics.record_post(
                content.raw.source_channel, 
                content.quality_score,
                content.processing_time_ms
            )
            logging.info(f"✅ Posted from {content.raw.source_channel} (Q: {content.quality_score:.2f})")
            await asyncio.sleep(2)
            return True
            
        except Exception as e:
            await self.metrics.record_error(content.raw.source_channel, f"Publish: {str(e)}")
            logging.error(f"Publish failed: {e}")
            return False
    
    async def run(self):
        logging.info("🚀 Starting OSINT Pipeline v2.0")
        logging.info(f"Config: DRY_RUN={self.config.DRY_RUN}, DEST={self.config.DEST_CHANNEL}")
        
        Path("temp").mkdir(exist_ok=True)
        Path("logs").mkdir(exist_ok=True)
        
        history = await self.fetch_history(limit=100)
        logging.info(f"Loaded {len(history)} historical messages for dedup")
        
        for h in history:
            h_hash = hashlib.sha256(h.encode()).hexdigest()[:32]
            self.dedup.seen_hashes.add(h_hash)
        
        for source in self.CANALE_SURSA:
            logging.info(f"📡 Processing: {source}")
            try:
                entity = await self.client.get_entity(source)
                count = 0
                async for msg in self.client.iter_messages(entity, limit=12):
                    processed = await self.process_message(msg, source)
                    if processed:
                        success = await self.publish(processed)
                        if success:
                            count += 1
                    await asyncio.sleep(0.5)
                logging.info(f"  → Posted {count} from {source}")
            except Exception as e:
                await self.metrics.record_error(source, str(e))
                logging.error(f"Failed processing {source}: {e}")
                continue
        
        logging.info("🏁 nexta_cloud_robot.py")

# ==========================================
# ENTRY POINT
# ==========================================
def setup_logging():
    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(message)s',
        handlers=[
            logging.FileHandler('logs/nexta_cloud_robot.py.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

def main():
    setup_logging()
    
    if SENTRY_AVAILABLE and os.getenv('SENTRY_DSN'):
        sentry_sdk.init(os.getenv('SENTRY_DSN'))
        logging.info("Sentry initialized")
    
    try:
        config = Config()
        config.validate()
    except ValueError as e:
        logging.error(f"Configuration error: {e}")
        raise
    
    async def run_pipeline():
        async with nexta_cloud_robot.py(config) as pipeline:
            await nexta_cloud_robot.py.run()
    
    asyncio.run(run_nexta_cloud_robot.py())

if __name__ == '__main__':
    main()
