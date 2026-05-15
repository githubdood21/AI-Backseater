
import sys
import time
from PIL import Image, ImageGrab
import io
import requests
import base64
import logging
import json
import csv
import sqlite3
import threading
import tempfile
import wave
import os
import re
import html
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path

KOKORO_REPO_PATH = Path(__file__).resolve().parent / "kokoro"
DLL_DIRECTORY_HANDLES = []
TTS_RUNTIME_ERROR = None


def preload_torch_before_qt():
    global TTS_RUNTIME_ERROR
    if str(KOKORO_REPO_PATH) not in sys.path:
        sys.path.insert(0, str(KOKORO_REPO_PATH))
    try:
        import torch
        torch_lib = Path(torch.__file__).resolve().parent / "lib"
        if torch_lib.exists() and hasattr(os, "add_dll_directory"):
            DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(torch_lib)))
    except Exception as e:
        TTS_RUNTIME_ERROR = e


preload_torch_before_qt()

from PyQt5.QtWidgets import (QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QWidget, QMenu,
                             QHBoxLayout, QFileDialog, QInputDialog, QMessageBox, QSizePolicy, QLayout, QStyle, QDialog, QLineEdit, QListWidget, QScrollArea, QTextEdit, QTimeEdit, QDialogButtonBox, QComboBox)
from PyQt5.QtCore import Qt, QTimer, QPoint, QRect, QThread, QObject, pyqtSignal, pyqtSlot, QSize, QTime
from PyQt5.QtGui import QFont, QPainter, QPen, QColor
import json
from queue import Queue


OOBA_OPENAI_URL = "http://localhost:5000/v1/chat/completions"
DEFAULT_ANALYSIS_INTERVAL_SECONDS = 30
DEFAULT_CONTEXT_SIZE_TOKENS = 4096
DEFAULT_MAX_RESPONSE_TOKENS = 900
CONTEXT_SAFETY_MARGIN_TOKENS = 512
KOKORO_SAMPLE_RATE = 24000
DEFAULT_INSTRUCTION_TEMPLATE = "ChatML"
DEFAULT_WEB_ADVICE_INTERVAL_MINUTES = 30
DEFAULT_WEB_ADVICE_QUERY = "video game beginner tips positioning resource management"
MAX_WEB_ADVICE_SNIPPETS = 6
LANGUAGE_GUARD_PROMPT = (
    "Output contract: Always respond in natural English only. "
    "Do not answer in Japanese, kana, kanji, romaji-heavy stylization, mojibake, or mixed-language roleplay. "
    "The character may be anime-inspired, but the spoken response must be clear English. "
    "If you use hidden reasoning or think tags, keep them separate from the final response. "
    "Only the final response will be shown to the user."
)
FILTERED_RESPONSE_TEXT = "Filtered model output; waiting for a clean final response."
THINKING_BLOCK_PATTERNS = [
    r"<think\b[^>]*>.*?</think>",
    r"<thinking\b[^>]*>.*?</thinking>",
    r"<thought\b[^>]*>.*?</thought>",
    r"<thoughts\b[^>]*>.*?</thoughts>",
    r"<reasoning\b[^>]*>.*?</reasoning>",
    r"\[think\].*?\[/think\]",
    r"\[thinking\].*?\[/thinking\]",
    r"\[reasoning\].*?\[/reasoning\]",
]
THINKING_PREFIX_PATTERN = re.compile(
    r"^\s*(?:thinking|reasoning|analysis|thoughts?)\s*:\s*.*?(?:\n\s*\n|(?:final|answer|response)\s*:)",
    re.IGNORECASE | re.DOTALL
)

CHARACTER_PRESETS = {
    "Bratty Coach": {
        "character": (
            "You are a bratty anime-style game companion watching the player play. "
            "You tease them for sloppy aim, missed reads, bad routing, panic decisions, and obvious mistakes, "
            "but your teasing is playful rather than cruel. Under the attitude, you are cute, loyal, and genuinely helpful. "
            "Stay in character as a smug little coach who cares about the player's success. "
            "Speak in natural English only, even though the style is anime-inspired. "
            "Do not be romantic or explicit. Do not insult protected traits or use hateful language. "
            "Keep replies short enough to be spoken aloud. Prioritize useful, situation-aware advice over generic commentary."
        ),
        "analysis": (
            "Look at the current game screenshot and react as the bratty companion. "
            "First notice the player's location, visible threats, objectives, resources, UI state, and any obvious tactical mistake. "
            "If there is useful advice, give it directly while teasing the player a little. "
            "If the player is doing fine, grudgingly admit it in a cute smug way. "
            "Avoid long descriptions; respond with 1-3 punchy English sentences."
        )
    }
}
DEFAULT_CHARACTER_PRESET = "Bratty Coach"

logging.basicConfig(filename='app.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')


def resize_image(image):
    """
    Resize the image if it exceeds 1.8 million pixels while maintaining aspect ratio.
    :param image: PIL Image object
    :return: Resized PIL Image object if necessary, otherwise the original image
    """
    MAX_PIXELS = 1_800_000  # 1.8 million pixels
    
    # Calculate current number of pixels
    current_pixels = image.width * image.height
    
    # If the image is already small enough, return it as is
    if current_pixels <= MAX_PIXELS:
        return image
    
    # Calculate the scale factor needed to reduce to 1.8 million pixels
    scale_factor = (MAX_PIXELS / current_pixels) ** 0.5
    
    # Calculate new dimensions, ensuring we round down
    new_width = int(image.width * scale_factor)
    new_height = int(image.height * scale_factor)
    
    # Resize the image using LANCZOS resampling
    return image.resize((new_width, new_height), Image.LANCZOS)


def encode_image_to_base64(image):
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8') 


def estimate_token_count(value):
    if isinstance(value, str):
        return max(1, len(value) // 4)
    if isinstance(value, list):
        return sum(estimate_token_count(item) for item in value)
    if isinstance(value, dict):
        return sum(estimate_token_count(item) for item in value.values())
    return max(1, len(str(value)) // 4)


def looks_like_garbled_language(text):
    if not text:
        return False
    kana_or_cjk = sum(
        1 for char in text
        if ('\u3040' <= char <= '\u30ff') or ('\u3400' <= char <= '\u9fff')
    )
    letters = sum(1 for char in text if char.isalpha())
    if kana_or_cjk >= 8:
        return True
    if letters and kana_or_cjk / letters > 0.25:
        return True
    return False


def strip_thinking_text(text):
    if not text:
        return ""
    cleaned = str(text)
    for pattern in THINKING_BLOCK_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = THINKING_PREFIX_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"^\s*(?:final|answer|response)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def prepare_kokoro_runtime():
    preload_torch_before_qt()
    if TTS_RUNTIME_ERROR:
        logging.warning(f"Unable to preload Kokoro/Torch runtime: {TTS_RUNTIME_ERROR}")


class HistoryManager:
    def __init__(self, db_path='analysis_history.db'):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS analysis_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                analysis_text TEXT,
                prompt TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def add_analysis(self, analysis_text, prompt):
        timestamp = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO analysis_history (timestamp, analysis_text, prompt) VALUES (?, ?, ?)',
                       (timestamp, analysis_text, prompt))
        conn.commit()
        conn.close()

    def get_history(self, limit=100):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        if limit is None:
            cursor.execute('SELECT * FROM analysis_history ORDER BY timestamp DESC')
        else:
            cursor.execute('SELECT * FROM analysis_history ORDER BY timestamp DESC LIMIT ?', (limit,))
        history = cursor.fetchall()
        conn.close()
        return history

    def search_history(self, query):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM analysis_history WHERE analysis_text LIKE ? OR prompt LIKE ? ORDER BY timestamp DESC',
                       (f'%{query}%', f'%{query}%'))
        results = cursor.fetchall()
        conn.close()
        return results

    def export_to_json(self, filename):
        history = self.get_history(limit=None)
        data = [{'id': item[0], 'timestamp': item[1], 'analysis_text': item[2], 'prompt': item[3]} for item in history]
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def export_to_csv(self, filename):
        history = self.get_history(limit=None)
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['ID', 'Timestamp', 'Analysis Text', 'Prompt'])
            writer.writerows(history)

    def get_analysis_by_timestamp(self, timestamp):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM analysis_history WHERE timestamp = ?', (timestamp,))
        analysis = cursor.fetchone()
        conn.close()
        return analysis


class OobaboogaClient:
    def __init__(self):
        self.oobabooga_url = OOBA_OPENAI_URL
        self.oobabooga_model = "local-model"
        self.instruction_template = DEFAULT_INSTRUCTION_TEMPLATE
        self.context_size_tokens = DEFAULT_CONTEXT_SIZE_TOKENS
        self.max_response_tokens = DEFAULT_MAX_RESPONSE_TOKENS

    def analyze(self, image, character_prompt, web_advice_text, memory_messages, current_prompt):
        image_base64 = encode_image_to_base64(image)
        image_url = f"data:image/jpeg;base64,{image_base64}"
        messages = self.build_messages(character_prompt, web_advice_text, memory_messages, current_prompt, image_url)
        payload = {
            "model": self.oobabooga_model,
            "messages": messages,
            "instruction_template": self.instruction_template or None,
            "max_tokens": self.max_response_tokens,
            "temperature": 0.2,
            "stream": False
        }

        try:
            response = requests.post(self.oobabooga_url, json=payload)
            response.raise_for_status()
            result = response.json()
            message = result["choices"][0]["message"]
            content = (
                message.get("content")
                or message.get("response")
                or message.get("text")
                or ""
            )
            if isinstance(content, list):
                content = " ".join(part.get("text", "") for part in content if isinstance(part, dict))
            return strip_thinking_text(content)
        except (requests.RequestException, KeyError, IndexError, TypeError) as e:
            logging.error(f"Error communicating with Oobabooga: {e}")
            return "Unable to analyze image at this time."

    def build_messages(self, character_prompt, web_advice_text, memory_messages, current_prompt, image_url):
        current_message = {
            "role": "user",
            "content": [
                {"type": "text", "text": current_prompt},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]
        }
        available_tokens = max(
            256,
            self.context_size_tokens - self.max_response_tokens - CONTEXT_SAFETY_MARGIN_TOKENS
        )
        messages = [
            {"role": "system", "content": character_prompt},
            {"role": "system", "content": LANGUAGE_GUARD_PROMPT}
        ]
        if web_advice_text:
            messages.append({
                "role": "system",
                "content": (
                    "Recent web advice snippets for gameplay reference. Use only if relevant to the current screenshot; "
                    "do not mention web search unless it matters.\n" + web_advice_text
                )
            })
        current_cost = estimate_token_count(messages) + estimate_token_count(current_prompt)
        selected_memory = []

        for message in reversed(memory_messages):
            message_cost = estimate_token_count(message)
            if current_cost + message_cost > available_tokens:
                break
            selected_memory.insert(0, message)
            current_cost += message_cost

        messages.extend(selected_memory)
        messages.append(current_message)
        return messages

    def infer_context_size(self):
        candidates = [
            self.oobabooga_url.replace("/v1/chat/completions", "/v1/internal/model/info"),
            self.oobabooga_url.replace("/v1/chat/completions", "/api/v1/model"),
        ]
        for url in candidates:
            try:
                response = requests.get(url, timeout=3)
                response.raise_for_status()
                detected = self.extract_context_size(response.json())
                if detected:
                    return detected
            except (requests.RequestException, ValueError, TypeError):
                continue
        return None

    def extract_context_size(self, data):
        if isinstance(data, dict):
            for key in ("truncation_length", "max_seq_len", "n_ctx", "context_length", "max_position_embeddings"):
                value = data.get(key)
                if isinstance(value, int) and value > 0:
                    return value
                if isinstance(value, str) and value.isdigit():
                    return int(value)
            for value in data.values():
                detected = self.extract_context_size(value)
                if detected:
                    return detected
        if isinstance(data, list):
            for item in data:
                detected = self.extract_context_size(item)
                if detected:
                    return detected
        return None


class AnalysisWorker(QObject):
    analysis_complete = pyqtSignal(str)
    alert_triggered = pyqtSignal(str, str)
    error_occurred = pyqtSignal(str)
    request_screenshot = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.running = True
        self.queue = Queue()
        self.overlay = None
        self.oobabooga_client = OobaboogaClient()
        self.capture_event = threading.Event()
        self.captured_image = None
        self.last_user_memory_message = None

    def set_overlay(self, overlay):
        self.overlay = overlay

    @pyqtSlot()
    def run_analysis(self):
        while self.running:
            try:
                current_time = datetime.now().time()
                if (self.overlay and 
                    not self.overlay.is_paused and 
                    not self.overlay.analysis_paused and
                    (not self.overlay.timer_start or 
                     (self.overlay.timer_start <= current_time < self.overlay.timer_end))):
                    image = self.capture_screenshot()

                    if image and image.getbbox() is not None:
                        self.configure_oobabooga_client()
                        user_memory_message = self.overlay.build_user_memory_message()
                        description = self.oobabooga_client.analyze(
                            image,
                            self.overlay.character_prompt,
                            self.overlay.build_web_advice_context(),
                            list(self.overlay.conversation_messages),
                            self.overlay.analysis_prompt
                        )
                        self.last_user_memory_message = user_memory_message
                        self.analysis_complete.emit(description)
                        
                        if self.overlay.alert_active:
                            self.check_alert_condition(image, description)
                    else:
                        logging.warning("Skipping analysis due to invalid screenshot")
                
                # Process any pending UI updates
                while not self.queue.empty():
                    func, args = self.queue.get()
                    func(*args)
            
            except Exception as e:
                self.error_occurred.emit(str(e))
            
            self.wait_for_next_cycle()

    def capture_screenshot(self):
        self.captured_image = None
        self.capture_event.clear()
        self.request_screenshot.emit()
        if not self.capture_event.wait(timeout=5):
            logging.warning("Timeout waiting for valid screenshot")
            return None
        return self.captured_image

    def set_captured_image(self, image):
        self.captured_image = image
        self.capture_event.set()

    def configure_oobabooga_client(self):
        self.oobabooga_client.oobabooga_url = self.overlay.oobabooga_url
        self.oobabooga_client.oobabooga_model = self.overlay.oobabooga_model
        self.oobabooga_client.instruction_template = self.overlay.instruction_template
        self.oobabooga_client.context_size_tokens = self.overlay.context_size_tokens
        self.oobabooga_client.max_response_tokens = self.overlay.max_response_tokens

    def wait_for_next_cycle(self):
        interval = DEFAULT_ANALYSIS_INTERVAL_SECONDS
        if self.overlay:
            interval = max(1, int(self.overlay.analysis_interval_seconds))
        end_time = time.time() + interval
        while self.running and time.time() < end_time:
            time.sleep(0.2)

    def check_alert_condition(self, image, analysis_text):
        check_prompt = f"Based on the image and the following analysis, determine if the condition '{self.overlay.alert_prompt}' is met. Respond with only 'Yes' or 'No'.\n\nImage analysis: {analysis_text}"
        
        self.configure_oobabooga_client()
        response = self.oobabooga_client.analyze(
            image,
            "You are a precise visual alert checker.",
            "",
            [],
            check_prompt
        )
        
        if response.strip().lower() == 'yes':
            self.alert_triggered.emit(self.overlay.alert_prompt, analysis_text)

    def stop(self):
        self.running = False

    def queue_function(self, func, *args):
        self.queue.put((func, args))


class SpeechManager(QObject):
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        prepare_kokoro_runtime()
        self.enabled = True
        self.lang_code = "a"
        self.voice = "af_heart"
        self.speed = 1.08
        self.queue = Queue()
        self.running = True
        self.pipeline = None
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def speak(self, text):
        if self.enabled and text:
            self.queue.put(text)

    def stop(self):
        self.running = False
        self.queue.put(None)
        self.thread.join(timeout=2)

    def configure(self, enabled, lang_code, voice, speed):
        self.enabled = enabled
        pipeline_changed = lang_code != self.lang_code
        self.lang_code = lang_code
        self.voice = voice
        self.speed = speed
        if pipeline_changed:
            self.pipeline = None

    def run(self):
        while self.running:
            text = self.queue.get()
            if text is None:
                continue
            if not self.enabled:
                continue
            try:
                self.speak_now(text)
            except Exception as e:
                self.enabled = False
                self.error_occurred.emit(f"TTS error: {e}")

    def speak_now(self, text):
        pipeline = self.get_pipeline()
        generator = pipeline(text, voice=self.voice, speed=self.speed, split_pattern=r'\n+')
        for _, _, audio in generator:
            if not self.running or audio is None:
                return
            self.play_audio(audio)

    def get_pipeline(self):
        if self.pipeline is None:
            prepare_kokoro_runtime()
            from kokoro import KPipeline
            self.pipeline = KPipeline(lang_code=self.lang_code)
        return self.pipeline

    def play_audio(self, audio):
        import winsound

        wav_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
                wav_path = temp_file.name
            self.write_wav(wav_path, audio)
            winsound.PlaySound(wav_path, winsound.SND_FILENAME)
        finally:
            if wav_path:
                try:
                    Path(wav_path).unlink(missing_ok=True)
                except OSError:
                    pass

    def write_wav(self, path, audio):
        import numpy as np

        samples = np.asarray(audio)
        samples = np.clip(samples, -1.0, 1.0)
        samples = (samples * 32767).astype(np.int16)
        with wave.open(path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(KOKORO_SAMPLE_RATE)
            wav_file.writeframes(samples.tobytes())


class WebAdviceManager(QObject):
    advice_updated = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.enabled = False
        self.query = DEFAULT_WEB_ADVICE_QUERY
        self.interval_minutes = DEFAULT_WEB_ADVICE_INTERVAL_MINUTES
        self.max_snippets = MAX_WEB_ADVICE_SNIPPETS
        self.running = True
        self.fetch_now_event = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def configure(self, enabled, query, interval_minutes, max_snippets):
        self.enabled = enabled
        self.query = query.strip() or DEFAULT_WEB_ADVICE_QUERY
        self.interval_minutes = max(5, int(interval_minutes))
        self.max_snippets = max(1, min(12, int(max_snippets)))
        if enabled:
            self.fetch_now()

    def fetch_now(self):
        self.fetch_now_event.set()

    def stop(self):
        self.running = False
        self.fetch_now_event.set()
        self.thread.join(timeout=2)

    def run(self):
        next_fetch = 0
        while self.running:
            now = time.time()
            if self.enabled and (self.fetch_now_event.is_set() or now >= next_fetch):
                self.fetch_now_event.clear()
                try:
                    snippets = self.fetch_advice()
                    if snippets:
                        self.advice_updated.emit(snippets)
                    next_fetch = time.time() + self.interval_minutes * 60
                except Exception as e:
                    self.error_occurred.emit(f"Web advice error: {e}")
                    next_fetch = time.time() + min(self.interval_minutes * 60, 300)
            self.fetch_now_event.wait(timeout=1)

    def fetch_advice(self):
        if self.query.startswith(("http://", "https://")):
            return self.fetch_page_snippets(self.query)[:self.max_snippets]
        response = requests.get(
            "https://api.duckduckgo.com/",
            params={
                "q": self.query,
                "format": "json",
                "no_html": 1,
                "skip_disambig": 1
            },
            timeout=12
        )
        response.raise_for_status()
        data = response.json()
        snippets = []
        abstract = data.get("AbstractText")
        abstract_url = data.get("AbstractURL")
        if abstract:
            snippets.append(self.format_snippet(abstract, abstract_url))
        self.collect_related_topics(data.get("RelatedTopics", []), snippets)
        if len(snippets) < 2:
            snippets.extend(self.fetch_search_result_snippets())
        return snippets[:self.max_snippets]

    def fetch_page_snippets(self, url):
        response = requests.get(
            url,
            headers={"User-Agent": "Screen-Analysis-Overlay/1.0"},
            timeout=12
        )
        response.raise_for_status()
        page = response.text
        candidates = []
        title_match = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
        if title_match:
            candidates.append(self.clean_html(title_match.group(1)))
        for pattern in (
            r"<h1[^>]*>(.*?)</h1>",
            r"<h2[^>]*>(.*?)</h2>",
            r"<p[^>]*>(.*?)</p>",
            r"<li[^>]*>(.*?)</li>",
        ):
            for match in re.findall(pattern, page, re.S | re.I):
                cleaned = self.clean_html(match)
                if 40 <= len(cleaned) <= 500:
                    candidates.append(cleaned)
                if len(candidates) >= self.max_snippets * 2:
                    break
            if len(candidates) >= self.max_snippets * 2:
                break
        source = urlparse(url).netloc
        unique = []
        seen = set()
        for candidate in candidates:
            key = candidate.lower()
            if key not in seen:
                seen.add(key)
                unique.append(self.format_snippet(candidate, f"https://{source}"))
            if len(unique) >= self.max_snippets:
                break
        return unique

    def fetch_search_result_snippets(self):
        response = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": self.query},
            headers={"User-Agent": "Screen-Analysis-Overlay/1.0"},
            timeout=12
        )
        response.raise_for_status()
        page = response.text
        snippets = []
        result_blocks = re.findall(r'<div class="result(?: results_links_deep)?".*?</div>\s*</div>', page, re.S)
        for block in result_blocks:
            if len(snippets) >= self.max_snippets:
                break
            title_match = re.search(r'class="result__a"[^>]*>(.*?)</a>', block, re.S)
            snippet_match = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, re.S)
            url_match = re.search(r'class="result__url"[^>]*>(.*?)</a>', block, re.S)
            title = self.clean_html(title_match.group(1)) if title_match else ""
            snippet = self.clean_html(snippet_match.group(1)) if snippet_match else ""
            source = self.clean_html(url_match.group(1)) if url_match else ""
            text = " - ".join(part for part in (title, snippet) if part)
            if text:
                snippets.append(self.format_snippet(text, f"https://{source}" if source else None))
        return snippets

    def clean_html(self, value):
        value = re.sub(r"<.*?>", "", value)
        value = html.unescape(value)
        return " ".join(value.split())

    def collect_related_topics(self, topics, snippets):
        for topic in topics:
            if len(snippets) >= self.max_snippets:
                return
            if "Topics" in topic:
                self.collect_related_topics(topic.get("Topics", []), snippets)
                continue
            text = topic.get("Text")
            if text:
                snippets.append(self.format_snippet(text, topic.get("FirstURL")))

    def format_snippet(self, text, url):
        if not url:
            return text
        domain = urlparse(url).netloc
        return f"{text} (source: {domain})"


class TransparentOverlay(QMainWindow):
    def __init__(self):
        super().__init__()
        self.capture_region = None
        self.is_capturing = False
        self.origin = None
        self.current = None
        self.character_preset_name = DEFAULT_CHARACTER_PRESET
        self.character_prompt = CHARACTER_PRESETS[DEFAULT_CHARACTER_PRESET]["character"]
        self.analysis_prompt = CHARACTER_PRESETS[DEFAULT_CHARACTER_PRESET]["analysis"]
        self.is_paused = False
        self.alert_prompt = ""
        self.alert_active = False
        self.current_image = None
        self.analysis_results = []
        self.conversation_messages = []
        self.context_size_tokens = DEFAULT_CONTEXT_SIZE_TOKENS
        self.max_response_tokens = DEFAULT_MAX_RESPONSE_TOKENS
        self.is_selecting_region = False  # New flag to track region selection state
        self.analysis_paused = False  # New flag to control analysis
        self.start_point = None
        self.end_point = None
        self.buttons_visible = True  # New attribute to track button visibility
        self.hide_during_screenshot = True  # New attribute to control overlay visibility during screenshots
        self.history_manager = HistoryManager()
        # Add new attributes for timer functionality
        self.timer_start = None
        self.timer_end = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_timer)
        self.timer.start(60000)  # Check every minute
        self.oobabooga_url = OOBA_OPENAI_URL
        self.oobabooga_model = "local-model"
        self.instruction_template = DEFAULT_INSTRUCTION_TEMPLATE
        self.analysis_interval_seconds = DEFAULT_ANALYSIS_INTERVAL_SECONDS
        self.tts_enabled = True
        self.tts_lang_code = "a"
        self.tts_voice = "af_heart"
        self.tts_speed = 1.08
        self.web_advice_enabled = False
        self.web_advice_query = DEFAULT_WEB_ADVICE_QUERY
        self.web_advice_interval_minutes = DEFAULT_WEB_ADVICE_INTERVAL_MINUTES
        self.web_advice_max_snippets = MAX_WEB_ADVICE_SNIPPETS
        self.web_advice_notes = []
        self.web_advice_updated_at = None
        self.initUI()

        self.speech_manager = SpeechManager()
        self.speech_manager.configure(self.tts_enabled, self.tts_lang_code, self.tts_voice, self.tts_speed)
        self.speech_manager.error_occurred.connect(self.handle_error)

        self.web_advice_manager = WebAdviceManager()
        self.web_advice_manager.configure(
            self.web_advice_enabled,
            self.web_advice_query,
            self.web_advice_interval_minutes,
            self.web_advice_max_snippets
        )
        self.web_advice_manager.advice_updated.connect(self.update_web_advice_notes)
        self.web_advice_manager.error_occurred.connect(self.handle_error)

        self.analysis_thread = QThread()
        self.analysis_worker = AnalysisWorker()
        self.analysis_worker.moveToThread(self.analysis_thread)
        self.analysis_thread.started.connect(self.analysis_worker.run_analysis)
        self.analysis_worker.analysis_complete.connect(self.handle_analysis_complete)
        self.analysis_worker.alert_triggered.connect(self.trigger_alert)
        self.analysis_worker.error_occurred.connect(self.handle_error)
        self.analysis_worker.request_screenshot.connect(self.take_screenshot)
        
        self.analysis_worker.set_overlay(self)
        self.analysis_thread.start()



        
    def initUI(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Set a fixed initial size for the overlay
        self.setFixedSize(1500, 800)
        
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        self.label = QLabel(self)
        self.label.setStyleSheet("color: white; background-color: rgba(0, 0, 0, 128); padding: 10px;")
        self.label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.label.setFont(QFont('Arial', 12))
        self.label.setWordWrap(True)
        main_layout.addWidget(self.label)
        
        self.button_widget = QWidget(self)
        self.button_layout = QFlowLayout(self.button_widget)
        self.button_layout.setSpacing(5)
        self.button_layout.setContentsMargins(5, 5, 5, 5)

        # Add new buttons for timer functionality
        set_timer_button = QPushButton("Set Timer", self)
        set_timer_button.clicked.connect(self.show_timer_dialog)
        self.button_layout.addWidget(set_timer_button)

        clear_timer_button = QPushButton("Clear Timer", self)
        clear_timer_button.clicked.connect(self.clear_timer)
        self.button_layout.addWidget(clear_timer_button)

        oobabooga_button = QPushButton("Oobabooga Settings", self)
        oobabooga_button.clicked.connect(self.show_oobabooga_settings_dialog)
        self.button_layout.addWidget(oobabooga_button)

        interval_button = QPushButton("Set Interval", self)
        interval_button.clicked.connect(self.show_interval_dialog)
        self.button_layout.addWidget(interval_button)

        tts_button = QPushButton("TTS Settings", self)
        tts_button.clicked.connect(self.show_tts_settings_dialog)
        self.button_layout.addWidget(tts_button)

        web_advice_button = QPushButton("Web Advice", self)
        web_advice_button.clicked.connect(self.show_web_advice_settings_dialog)
        self.button_layout.addWidget(web_advice_button)
        
        buttons = [
            ("Select Region", self.select_region),
            ("Character/Prompt", self.show_prompt_dialog),
            ("Pause", self.toggle_pause_resume),
            ("Save Results", self.save_results),
            ("Set Alert", self.set_alert_prompt),
            ("Resize Overlay", self.resize_overlay),
            ("Toggle Hide", self.toggle_hide_during_screenshot)  # New button
        ]

        # Add new buttons
        view_history_button = QPushButton("View History", self)
        view_history_button.clicked.connect(self.show_history_dialog)
        self.button_layout.addWidget(view_history_button)
        
        export_button = QPushButton("Export History", self)
        export_button.clicked.connect(self.show_export_dialog)
        self.button_layout.addWidget(export_button)
        
        for text, slot in buttons:
            button = QPushButton(text, self)
            button.clicked.connect(slot)
            button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            if text == "Pause":
                self.pause_resume_button = button  # Store reference to Pause/Resume button
            self.button_layout.addWidget(button)
        
        main_layout.addWidget(self.button_widget)
        
        # Set layout margins and spacing
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        self.show()


    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle_buttons_visibility()

    def toggle_buttons_visibility(self):
        self.buttons_visible = not self.buttons_visible
        self.button_widget.setVisible(self.buttons_visible)

    def resize_overlay(self):
        new_width, ok1 = QInputDialog.getInt(self, 'Resize Overlay', 'Enter new width:', self.width(), 100, 2000)
        if ok1:
            new_height, ok2 = QInputDialog.getInt(self, 'Resize Overlay', 'Enter new height:', self.height(), 100, 2000)
            if ok2:
                self.setFixedSize(new_width, new_height)
                self.update_text(f"Overlay resized to {new_width}x{new_height}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.button_widget.setFixedWidth(self.width() - 10)  # Adjust for margins         

    
    def update_text(self, text):
        self.label.setText(text)
        self.analysis_results.append(text)
        # Automatically save the analysis to history
        self.history_manager.add_analysis(text, self.analysis_prompt)

    @pyqtSlot(str)
    def handle_analysis_complete(self, text):
        text = strip_thinking_text(text)
        if not text:
            logging.warning("Rejected empty LLM output after stripping thinking text")
            self.label.setText(FILTERED_RESPONSE_TEXT)
            return
        if looks_like_garbled_language(text):
            logging.warning(f"Rejected likely garbled/non-English LLM output: {text[:200]}")
            self.conversation_messages.clear()
            self.label.setText(FILTERED_RESPONSE_TEXT)
            return
        self.update_text(text)
        user_message = self.analysis_worker.last_user_memory_message or self.build_user_memory_message()
        self.add_memory_exchange(user_message, text)
        self.speech_manager.speak(text)

    def build_user_memory_message(self):
        timestamp = datetime.now().strftime("%H:%M:%S")
        return {
            "role": "user",
            "content": f"[{timestamp}] Current screenshot analysis request: {self.analysis_prompt}"
        }

    def add_memory_exchange(self, user_message, assistant_text):
        self.conversation_messages.append(user_message)
        self.conversation_messages.append({"role": "assistant", "content": assistant_text})
        self.trim_memory_messages()

    def trim_memory_messages(self):
        available_tokens = max(
            256,
            self.context_size_tokens - self.max_response_tokens - CONTEXT_SAFETY_MARGIN_TOKENS
        )
        base_cost = estimate_token_count(self.character_prompt) + estimate_token_count(self.analysis_prompt)
        kept_messages = []
        total = base_cost

        for message in reversed(self.conversation_messages):
            message_cost = estimate_token_count(message)
            if total + message_cost > available_tokens:
                break
            kept_messages.insert(0, message)
            total += message_cost

        self.conversation_messages = kept_messages

    @pyqtSlot(list)
    def update_web_advice_notes(self, snippets):
        self.web_advice_notes = snippets[:self.web_advice_max_snippets]
        self.web_advice_updated_at = datetime.now()
        self.update_text(f"Web advice updated: {len(self.web_advice_notes)} snippets")

    def build_web_advice_context(self):
        if not self.web_advice_enabled or not self.web_advice_notes:
            return ""
        timestamp = self.web_advice_updated_at.isoformat(timespec="minutes") if self.web_advice_updated_at else "unknown"
        lines = [f"Query: {self.web_advice_query}", f"Fetched: {timestamp}"]
        lines.extend(f"- {snippet}" for snippet in self.web_advice_notes)
        return "\n".join(lines)

    def show_history_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Analysis History")
        dialog.setMinimumSize(600, 400)  # Set a minimum size for better usability
        layout = QVBoxLayout(dialog)

        # Add search box
        search_box = QLineEdit(dialog)
        search_box.setPlaceholderText("Search history...")
        layout.addWidget(search_box)

        # Add list widget to display history
        list_widget = QListWidget(dialog)
        layout.addWidget(list_widget)

        # Function to update the list widget
        def update_list(query=''):
            list_widget.clear()
            if query:
                history = self.history_manager.search_history(query)
            else:
                history = self.history_manager.get_history()
            for item in history:
                list_widget.addItem(f"{item[1]}: {item[2][:50]}...")

        # Connect search box to update function
        search_box.textChanged.connect(update_list)

        # Function to open selected analysis
        def open_analysis(item):
            selected_text = item.text()
            parts = selected_text.split(":")  # Split the string into parts
            timestamp = parts[0] + ":" + parts[1] + ":" + parts[2]  # Reconstruct the timestamp
            print(timestamp)
            full_analysis = self.history_manager.get_analysis_by_timestamp(timestamp)
            if full_analysis:
                self.show_analysis_detail(full_analysis)

        # Connect list widget item click to open_analysis function
        list_widget.itemClicked.connect(open_analysis)

        # Initial population of the list
        update_list()

        dialog.exec_()

    def show_analysis_detail(self, analysis):
        detail_dialog = QDialog(self)
        detail_dialog.setWindowTitle(f"Analysis Detail - {analysis[1]}")
        detail_dialog.setMinimumSize(800, 600)  # Set a minimum size for better readability
        layout = QVBoxLayout(detail_dialog)

        # Create a scroll area for the text
        scroll_area = QScrollArea(detail_dialog)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        # Create a widget to hold the text
        content_widget = QWidget()
        scroll_area.setWidget(content_widget)
        content_layout = QVBoxLayout(content_widget)

        # Add timestamp
        timestamp_label = QLabel(f"Timestamp: {analysis[1]}")
        timestamp_label.setStyleSheet("font-weight: bold;")
        content_layout.addWidget(timestamp_label)

        # Add prompt
        prompt_label = QLabel(f"Prompt: {analysis[3]}")
        prompt_label.setStyleSheet("font-weight: bold;")
        content_layout.addWidget(prompt_label)

        # Add analysis text
        analysis_text = QTextEdit()
        analysis_text.setPlainText(analysis[2])
        analysis_text.setReadOnly(True)
        content_layout.addWidget(analysis_text)

        detail_dialog.exec_()

    def show_export_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Export History")
        layout = QVBoxLayout(dialog)

        json_button = QPushButton("Export as JSON", dialog)
        csv_button = QPushButton("Export as CSV", dialog)

        layout.addWidget(json_button)
        layout.addWidget(csv_button)

        def export_json():
            filename, _ = QFileDialog.getSaveFileName(self, "Save JSON", "", "JSON Files (*.json)")
            if filename:
                self.history_manager.export_to_json(filename)
                QMessageBox.information(self, "Export Successful", f"Data exported to {filename}")

        def export_csv():
            filename, _ = QFileDialog.getSaveFileName(self, "Save CSV", "", "CSV Files (*.csv)")
            if filename:
                self.history_manager.export_to_csv(filename)
                QMessageBox.information(self, "Export Successful", f"Data exported to {filename}")

        json_button.clicked.connect(export_json)
        csv_button.clicked.connect(export_csv)

        dialog.exec_()
    
    @pyqtSlot(str, str)
    def trigger_alert(self, alert_prompt, analysis_text):
        QTimer.singleShot(0, lambda: self._show_alert(alert_prompt, analysis_text))

    def _show_alert(self, alert_prompt, analysis_text):
        alert = QMessageBox(self)
        alert.setIcon(QMessageBox.Warning)
        alert.setText("Alert Condition Met!")
        alert.setInformativeText(f"The condition '{alert_prompt}' was detected.")
        alert.setDetailedText(analysis_text)
        alert.setWindowTitle("Image Analysis Alert")
        alert.show()

    @pyqtSlot(str)
    def handle_error(self, error_message):
        logging.error(f"Error in analysis thread: {error_message}")
        self.update_text(f"An error occurred: {error_message}")

    def closeEvent(self, event):
        self.analysis_worker.stop()
        self.analysis_thread.quit()
        self.analysis_thread.wait()
        self.speech_manager.stop()
        self.web_advice_manager.stop()
        super().closeEvent(event)
    

    def toggle_pause_resume(self):
        self.is_paused = not self.is_paused
        button_text = "Resume" if self.is_paused else "Pause"
        self.pause_resume_button.setText(button_text)  # Update button text
        status = "paused" if self.is_paused else "resumed"
        self.update_text(f"Capture and analysis {status}")
        
        if not self.is_paused:
            self.is_selecting_region = False

    def toggle_hide_during_screenshot(self):
        self.hide_during_screenshot = not self.hide_during_screenshot
        status = "hidden" if self.hide_during_screenshot else "visible"
        self.update_text(f"Overlay will be {status} during screenshots")
    
    def save_results(self):
        if not self.analysis_results:
            self.update_text("No results to save.")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Analysis Results", "", "Text Files (*.txt);;All Files (*)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as file:
                    for result in self.analysis_results:
                        file.write(result + "\n\n")
                self.update_text(f"Results saved to {file_path}")
            except Exception as e:
                self.update_text(f"Error saving results: {str(e)}")

    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.offset = event.pos()
        elif event.button() == Qt.RightButton:
            self.show_context_menu(event.pos())
    
    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.move(self.mapToGlobal(event.pos() - self.offset))
    
    def show_context_menu(self, pos):
        context_menu = QMenu(self)
        hide_buttons = context_menu.addAction("Hide Buttons")
        view_history = context_menu.addAction("View History")
        export_history = context_menu.addAction("Export History")
        update_prompt_action = context_menu.addAction("Character/Prompt")
        oobabooga_settings_action = context_menu.addAction("Oobabooga Settings")
        set_interval_action = context_menu.addAction("Set Interval")
        tts_settings_action = context_menu.addAction("TTS Settings")
        web_advice_action = context_menu.addAction("Web Advice")
        toggle_pause_action = context_menu.addAction("Pause/Resume")
        save_results_action = context_menu.addAction("Save Results")
        set_alert_action = context_menu.addAction("Set Alert Condition")
        clear_alert_action = context_menu.addAction("Clear Alert")
        resize_action = context_menu.addAction("Resize Overlay")
        toggle_hide = context_menu.addAction("Toggle Hide")
        exit_action = context_menu.addAction("Exit Application")
        
        action = context_menu.exec_(self.mapToGlobal(pos))
        if action == hide_buttons:
            self.toggle_buttons_visibility()
        elif action == update_prompt_action:
            self.show_prompt_dialog()
        elif action == oobabooga_settings_action:
            self.show_oobabooga_settings_dialog()
        elif action == set_interval_action:
            self.show_interval_dialog()
        elif action == tts_settings_action:
            self.show_tts_settings_dialog()
        elif action == web_advice_action:
            self.show_web_advice_settings_dialog()
        elif action == toggle_pause_action:
            self.toggle_pause_resume()
        elif action == view_history:
            self.show_history_dialog()
        elif action == export_history:
            self.show_export_dialog()
        elif action == save_results_action:
            self.save_results()
        elif action == set_alert_action:
            self.set_alert_prompt()
        elif action == clear_alert_action:
            self.clear_alert()
        elif action == resize_action:
            self.resize_overlay()
        elif action == toggle_hide: 
            self.toggle_hide_during_screenshot()
        elif action == exit_action:
            QApplication.quit()
    
    def select_region(self):
        self.is_selecting_region = True
        self.analysis_paused = True
        self.hide()
        self.start_point = None
        self.end_point = None
        QTimer.singleShot(100, self.start_region_selection)
    
    def start_region_selection(self):
        screen = QApplication.primaryScreen()
        self.original_screenshot = screen.grabWindow(0)
        self.select_window = QMainWindow()
        self.select_window.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.select_window.setGeometry(screen.geometry())
        self.select_window.setAttribute(Qt.WA_TranslucentBackground)
        self.select_window.show()
        self.select_window.setMouseTracking(True)
        self.select_window.mousePressEvent = self.region_select_press
        self.select_window.mouseMoveEvent = self.region_select_move
        self.select_window.mouseReleaseEvent = self.region_select_release
        self.select_window.paintEvent = self.region_select_paint



    
    def region_select_press(self, event):
        self.start_point = event.pos()
    
    def region_select_move(self, event):
        if self.start_point:
            self.end_point = event.pos()
            self.select_window.update()
    
    def region_select_release(self, event):
        self.end_point = event.pos()
        if self.start_point and self.end_point:
            self.capture_region = QRect(self.start_point, self.end_point).normalized()
            logging.info(f"Region selected: {self.capture_region}")
            self.update_text(f"Region selected: {self.capture_region}")
        self.is_selecting_region = False
        self.analysis_paused = False
        self.select_window.close()
        self.show()
        self.trigger_analysis()


    def trigger_analysis(self):
        if hasattr(self, 'analysis_worker'):
            self.analysis_worker.request_screenshot.emit() 
    
    def region_select_paint(self, event):
        painter = QPainter(self.select_window)
        painter.drawPixmap(self.select_window.rect(), self.original_screenshot)
        
        if self.start_point and self.end_point:
            painter.setPen(QPen(Qt.red, 2, Qt.SolidLine))
            painter.setBrush(QColor(255, 0, 0, 50))  # Semi-transparent red
            painter.drawRect(QRect(self.start_point, self.end_point).normalized())
        
        # Draw instructions
        painter.setPen(Qt.white)
        painter.setFont(QFont('Arial', 14))
        painter.drawText(10, 30, "Click and drag to select a region. Press Esc to cancel.")

    def update_analysis_prompt(self, new_prompt):
        self.analysis_prompt = new_prompt
        print(f"Analysis prompt updated to: {self.analysis_prompt}")

    
    def show_prompt_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Character and Prompt")
        dialog.setMinimumSize(700, 500)
        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel("Character preset:"))
        preset_combo = QComboBox(dialog)
        preset_combo.addItem("Custom")
        for preset_name in CHARACTER_PRESETS:
            preset_combo.addItem(preset_name)
        preset_combo.setCurrentText(
            self.character_preset_name if self.character_preset_name in CHARACTER_PRESETS else "Custom"
        )
        layout.addWidget(preset_combo)

        layout.addWidget(QLabel("Character prompt:"))
        character_text = QTextEdit(dialog)
        character_text.setPlainText(self.character_prompt)
        layout.addWidget(character_text)

        layout.addWidget(QLabel("Current screenshot prompt:"))
        analysis_text = QTextEdit(dialog)
        analysis_text.setPlainText(self.analysis_prompt)
        layout.addWidget(analysis_text)

        clear_memory_button = QPushButton("Clear Memory", dialog)
        layout.addWidget(clear_memory_button)
        clear_memory_button.clicked.connect(lambda: self.clear_conversation_memory(dialog))

        def apply_preset(preset_name):
            if preset_name == "Custom":
                return
            preset = CHARACTER_PRESETS[preset_name]
            character_text.setPlainText(preset["character"])
            analysis_text.setPlainText(preset["analysis"])

        preset_combo.currentTextChanged.connect(apply_preset)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        if dialog.exec_() == QDialog.Accepted:
            self.character_prompt = character_text.toPlainText().strip() or self.character_prompt
            self.analysis_prompt = analysis_text.toPlainText().strip() or self.analysis_prompt
            selected_preset = preset_combo.currentText()
            if selected_preset in CHARACTER_PRESETS:
                preset = CHARACTER_PRESETS[selected_preset]
                if self.character_prompt == preset["character"] and self.analysis_prompt == preset["analysis"]:
                    self.character_preset_name = selected_preset
                else:
                    self.character_preset_name = "Custom"
            else:
                self.character_preset_name = "Custom"
            self.trim_memory_messages()
            self.update_text("Character and screenshot prompt updated")

    def clear_conversation_memory(self, parent=None):
        self.conversation_messages.clear()
        QMessageBox.information(parent or self, "Memory Cleared", "Conversation memory has been cleared.")

    def show_tts_settings_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("TTS Settings")
        layout = QVBoxLayout(dialog)

        enabled_combo = QComboBox(dialog)
        enabled_combo.addItems(["Enabled", "Disabled"])
        enabled_combo.setCurrentText("Enabled" if self.tts_enabled else "Disabled")
        layout.addWidget(QLabel("Voice output:"))
        layout.addWidget(enabled_combo)

        lang_input = QLineEdit(self.tts_lang_code)
        layout.addWidget(QLabel("Kokoro language code:"))
        layout.addWidget(lang_input)

        voice_input = QLineEdit(self.tts_voice)
        layout.addWidget(QLabel("Kokoro voice:"))
        layout.addWidget(voice_input)

        speed_input = QLineEdit(str(self.tts_speed))
        layout.addWidget(QLabel("Speed:"))
        layout.addWidget(speed_input)

        test_button = QPushButton("Test Voice", dialog)
        layout.addWidget(test_button)

        def apply_tts_settings():
            self.tts_enabled = enabled_combo.currentText() == "Enabled"
            self.tts_lang_code = lang_input.text().strip() or "a"
            self.tts_voice = voice_input.text().strip() or "af_heart"
            try:
                self.tts_speed = max(0.5, min(2.0, float(speed_input.text().strip())))
            except ValueError:
                self.tts_speed = 1.08
            self.speech_manager.configure(
                self.tts_enabled,
                self.tts_lang_code,
                self.tts_voice,
                self.tts_speed
            )

        def test_voice():
            apply_tts_settings()
            self.speech_manager.speak("Hmph. Fine, I can talk now. Try not to embarrass yourself too badly.")

        test_button.clicked.connect(test_voice)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        if dialog.exec_() == QDialog.Accepted:
            apply_tts_settings()
            status = "enabled" if self.tts_enabled else "disabled"
            self.update_text(f"TTS {status}: {self.tts_voice}")

    def show_web_advice_settings_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Web Advice")
        dialog.setMinimumSize(600, 360)
        layout = QVBoxLayout(dialog)

        enabled_combo = QComboBox(dialog)
        enabled_combo.addItems(["Disabled", "Enabled"])
        enabled_combo.setCurrentText("Enabled" if self.web_advice_enabled else "Disabled")
        layout.addWidget(QLabel("Periodic web advice:"))
        layout.addWidget(enabled_combo)

        query_input = QLineEdit(self.web_advice_query)
        layout.addWidget(QLabel("Search query, game/topic, or guide URL:"))
        layout.addWidget(query_input)

        interval_input = QLineEdit(str(self.web_advice_interval_minutes))
        layout.addWidget(QLabel("Fetch interval minutes:"))
        layout.addWidget(interval_input)

        snippets_input = QLineEdit(str(self.web_advice_max_snippets))
        layout.addWidget(QLabel("Max snippets kept:"))
        layout.addWidget(snippets_input)

        preview = QTextEdit(dialog)
        preview.setReadOnly(True)
        preview.setPlainText("\n".join(self.web_advice_notes) if self.web_advice_notes else "No web advice fetched yet.")
        layout.addWidget(preview)

        fetch_now_button = QPushButton("Fetch Now", dialog)
        layout.addWidget(fetch_now_button)

        def apply_web_advice_settings(fetch_now=False):
            self.web_advice_enabled = enabled_combo.currentText() == "Enabled"
            self.web_advice_query = query_input.text().strip() or DEFAULT_WEB_ADVICE_QUERY
            try:
                self.web_advice_interval_minutes = max(5, int(interval_input.text().strip()))
            except ValueError:
                self.web_advice_interval_minutes = DEFAULT_WEB_ADVICE_INTERVAL_MINUTES
            try:
                self.web_advice_max_snippets = max(1, min(12, int(snippets_input.text().strip())))
            except ValueError:
                self.web_advice_max_snippets = MAX_WEB_ADVICE_SNIPPETS
            self.web_advice_manager.configure(
                self.web_advice_enabled,
                self.web_advice_query,
                self.web_advice_interval_minutes,
                self.web_advice_max_snippets
            )
            if fetch_now:
                self.web_advice_enabled = True
                enabled_combo.setCurrentText("Enabled")
                self.web_advice_manager.configure(
                    True,
                    self.web_advice_query,
                    self.web_advice_interval_minutes,
                    self.web_advice_max_snippets
                )
                self.update_text("Fetching web advice...")

        fetch_now_button.clicked.connect(lambda: apply_web_advice_settings(fetch_now=True))

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        if dialog.exec_() == QDialog.Accepted:
            apply_web_advice_settings()
            status = "enabled" if self.web_advice_enabled else "disabled"
            self.update_text(f"Web advice {status}: {self.web_advice_query}")

    def show_interval_dialog(self):
        interval, ok = QInputDialog.getInt(
            self,
            'Set Analysis Interval',
            'Seconds between automatic screenshots:',
            self.analysis_interval_seconds,
            1,
            3600
        )
        if ok:
            self.analysis_interval_seconds = interval
            self.update_text(f"Analysis interval set to {interval} seconds")

    def set_alert_prompt(self):
        prompt, ok = QInputDialog.getText(self, 'Set Alert Prompt', 
                                          'Enter alert condition (e.g., "Can you see birds?"):')
        if ok and prompt:
            self.alert_prompt = prompt
            self.alert_active = True
            self.update_text(f"Alert set for condition: {self.alert_prompt}")
        elif ok:
            self.alert_prompt = ""
            self.alert_active = False
            self.update_text("Alert cleared")

    def clear_alert(self):
        self.alert_prompt = ""
        self.alert_active = False
        self.update_text("Alert condition cleared")

    def show_timer_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Set Analysis Timer")
        layout = QVBoxLayout(dialog)

        start_time_edit = QTimeEdit(dialog)
        start_time_edit.setDisplayFormat("HH:mm")
        layout.addWidget(QLabel("Start Time:"))
        layout.addWidget(start_time_edit)

        end_time_edit = QTimeEdit(dialog)
        end_time_edit.setDisplayFormat("HH:mm")
        layout.addWidget(QLabel("End Time:"))
        layout.addWidget(end_time_edit)

        button_box = QHBoxLayout()
        ok_button = QPushButton("OK", dialog)
        cancel_button = QPushButton("Cancel", dialog)
        button_box.addWidget(ok_button)
        button_box.addWidget(cancel_button)
        layout.addLayout(button_box)

        ok_button.clicked.connect(dialog.accept)
        cancel_button.clicked.connect(dialog.reject)

        if dialog.exec_() == QDialog.Accepted:
            self.timer_start = start_time_edit.time().toPyTime()
            self.timer_end = end_time_edit.time().toPyTime()
            self.update_text(f"Timer set: {self.timer_start.strftime('%H:%M')} - {self.timer_end.strftime('%H:%M')}")

            self.check_timer()  # Immediately check if we should start/stop analysis

    def clear_timer(self):
        self.timer_start = None
        self.timer_end = None
        self.update_text("Timer cleared")
        self.check_timer()

    def check_timer(self):
        current_time = datetime.now().time()
        if self.timer_start and self.timer_end:
            if self.timer_start <= current_time < self.timer_end:
                if self.is_paused:
                    self.toggle_pause_resume()
                    self.update_text("Analysis started due to timer")
            else:
                if not self.is_paused:
                    self.toggle_pause_resume()
                    self.update_text("Analysis paused due to timer")



    @pyqtSlot()
    def take_screenshot(self):
        if self.is_selecting_region:
            logging.info("Region selection in progress, skipping screenshot")
            return
        
        if self.hide_during_screenshot:
            self.hide()  # Hide the overlay only if hide_during_screenshot is True
        QApplication.processEvents()  # Ensure the hide takes effect

        try:
            if self.capture_region and not self.is_selecting_region:
                # Convert QRect to screen coordinates
                screen = QApplication.primaryScreen()
                screen_geometry = screen.geometry()
                left = self.capture_region.left() + screen_geometry.left()
                top = self.capture_region.top() + screen_geometry.top()
                right = self.capture_region.right() + screen_geometry.left()
                bottom = self.capture_region.bottom() + screen_geometry.top()

                # Use ImageGrab for screen capture
                img = ImageGrab.grab(bbox=(left, top, right, bottom))
                logging.info(f"Screenshot taken of selected region: {left},{top},{right},{bottom}")
            else:
                img = ImageGrab.grab()
                logging.info("Full screen screenshot taken")

            if self.hide_during_screenshot:
                self.show()  # Show the overlay immediately after taking the screenshot

            self.current_image = resize_image(img)
            
            if self.current_image.getbbox() is None:
                logging.warning("Captured image is empty")
            else:
                logging.info(f"Captured image size: {self.current_image.size}")

        except Exception as e:
            logging.error(f"Error taking screenshot: {str(e)}")
            self.current_image = None
        finally:
            if self.hide_during_screenshot:
                self.show()  # Show the overlay again only if it was hidden
            self.analysis_worker.set_captured_image(self.current_image)

    def show_oobabooga_settings_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Oobabooga Settings")
        layout = QVBoxLayout(dialog)

        oobabooga_url_label = QLabel("Oobabooga OpenAI-compatible URL:")
        oobabooga_url_input = QLineEdit(self.oobabooga_url)
        layout.addWidget(oobabooga_url_label)
        layout.addWidget(oobabooga_url_input)

        oobabooga_model_label = QLabel("Oobabooga Model:")
        oobabooga_model_input = QLineEdit(self.oobabooga_model)
        layout.addWidget(oobabooga_model_label)
        layout.addWidget(oobabooga_model_input)

        instruction_template_label = QLabel("Instruction template:")
        instruction_template_input = QLineEdit(self.instruction_template)
        layout.addWidget(instruction_template_label)
        layout.addWidget(instruction_template_input)

        context_label = QLabel("Context size tokens:")
        context_input = QLineEdit(str(self.context_size_tokens))
        layout.addWidget(context_label)
        layout.addWidget(context_input)

        max_response_label = QLabel("Max response tokens:")
        max_response_input = QLineEdit(str(self.max_response_tokens))
        layout.addWidget(max_response_label)
        layout.addWidget(max_response_input)

        detect_context_button = QPushButton("Detect Context Size", dialog)
        layout.addWidget(detect_context_button)

        def detect_context_size():
            client = OobaboogaClient()
            client.oobabooga_url = oobabooga_url_input.text().strip() or OOBA_OPENAI_URL
            client.oobabooga_model = oobabooga_model_input.text().strip() or "local-model"
            client.instruction_template = instruction_template_input.text().strip() or DEFAULT_INSTRUCTION_TEMPLATE
            detected = client.infer_context_size()
            if detected:
                context_input.setText(str(detected))
                QMessageBox.information(dialog, "Context Size Detected", f"Detected context size: {detected} tokens")
            else:
                QMessageBox.warning(dialog, "Context Size Not Found", "Could not detect context size from Oobabooga. Please set it manually.")

        detect_context_button.clicked.connect(detect_context_size)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        if dialog.exec_() == QDialog.Accepted:
            self.oobabooga_url = oobabooga_url_input.text().strip() or OOBA_OPENAI_URL
            self.oobabooga_model = oobabooga_model_input.text().strip() or "local-model"
            self.instruction_template = instruction_template_input.text().strip() or DEFAULT_INSTRUCTION_TEMPLATE
            try:
                self.context_size_tokens = max(512, int(context_input.text().strip()))
            except ValueError:
                self.context_size_tokens = DEFAULT_CONTEXT_SIZE_TOKENS
            try:
                self.max_response_tokens = max(32, int(max_response_input.text().strip()))
            except ValueError:
                self.max_response_tokens = DEFAULT_MAX_RESPONSE_TOKENS
            self.trim_memory_messages()
            self.update_text(f"Oobabooga model set to: {self.oobabooga_model} ({self.instruction_template})")
            

class QFlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing=-1):
        super(QFlowLayout, self).__init__(parent)
        self.itemList = []
        self.m_hSpace = spacing
        self.m_vSpace = spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self.itemList.append(item)

    def horizontalSpacing(self):
        if self.m_hSpace >= 0:
            return self.m_hSpace
        else:
            return self.smartSpacing(QStyle.PM_LayoutHorizontalSpacing)

    def verticalSpacing(self):
        if self.m_vSpace >= 0:
            return self.m_vSpace
        else:
            return self.smartSpacing(QStyle.PM_LayoutVerticalSpacing)

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self.doLayout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super(QFlowLayout, self).setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())
        size += QSize(2 * self.contentsMargins().top(), 2 * self.contentsMargins().top())
        return size

    def doLayout(self, rect, testOnly):
        x = rect.x()
        y = rect.y()
        lineHeight = 0

        for item in self.itemList:
            wid = item.widget()
            spaceX = self.horizontalSpacing()
            if spaceX == -1:
                spaceX = wid.style().layoutSpacing(
                    QSizePolicy.PushButton, QSizePolicy.PushButton, Qt.Horizontal)
            spaceY = self.verticalSpacing()
            if spaceY == -1:
                spaceY = wid.style().layoutSpacing(
                    QSizePolicy.PushButton, QSizePolicy.PushButton, Qt.Vertical)
            
            nextX = x + item.sizeHint().width() + spaceX
            if nextX - spaceX > rect.right() and lineHeight > 0:
                x = rect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())

        return y + lineHeight - rect.y()

    def smartSpacing(self, pm):
        parent = self.parent()
        if not parent:
            return -1
        elif parent.isWidgetType():
            return parent.style().pixelMetric(pm, None, parent)
        else:
            return parent.spacing()
        
    

def main():
    app = QApplication(sys.argv)
    overlay = TransparentOverlay()
    overlay.show()

    # Ensure the analysis worker is properly connected
    overlay.analysis_worker.set_overlay(overlay)
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 
