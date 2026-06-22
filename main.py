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
                             QHBoxLayout, QFileDialog, QInputDialog, QMessageBox, QSizePolicy, QLayout, QStyle, QDialog, QLineEdit, QListWidget, QScrollArea, QTextEdit, QTimeEdit, QDialogButtonBox, QComboBox, QSystemTrayIcon, QFrame)
from PyQt5.QtCore import Qt, QTimer, QPoint, QRect, QThread, QObject, pyqtSignal, pyqtSlot, QSize, QTime
from PyQt5.QtGui import QFont, QPainter, QPen, QColor, QIcon, QPixmap, QFontDatabase, QCursor, QPalette
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


# ================================
# MODERN WINDOWS 11 STYLESHEET
# ================================

WINDOWS_11_STYLESHEET = """
/* Global */
QWidget {
    font-family: 'Segoe UI Variable Display', 'Segoe UI', 'Microsoft YaHei UI', sans-serif;
    color: #e2e8f0;
    font-size: 13px;
}

QMainWindow {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1e1e2e, stop:1 #181825);
}

QDialog {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1e1e2e, stop:1 #181825);
    min-width: 400px;
}

QLabel {
    color: #cbd5e1;
    background: transparent;
    padding: 2px 0px;
}

QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #334155, stop:1 #2d3748);
    color: #e2e8f0;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 7px 16px;
    font-size: 12px;
    font-weight: 600;
    min-height: 20px;
}

QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3b4f6f, stop:1 #374151);
    border: 1px solid #60a5fa;
}

QPushButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1e3a5f, stop:1 #1a2d4a);
    border: 1px solid #3b82f6;
}

QPushButton:disabled {
    background: #1e293b;
    color: #475569;
    border: 1px solid #334155;
}

QLineEdit {
    background: #0f172a;
    color: #e2e8f0;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
    selection-background-color: #3b82f6;
    selection-color: white;
}

QLineEdit:focus {
    border: 1px solid #60a5fa;
    background: #0f172a;
}

QTextEdit {
    background: #0f172a;
    color: #e2e8f0;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 8px 10px;
    font-size: 13px;
    selection-background-color: #3b82f6;
    selection-color: white;
}

QTextEdit:focus {
    border: 1px solid #60a5fa;
}

QComboBox {
    background: #0f172a;
    color: #e2e8f0;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 7px 12px;
    font-size: 13px;
    min-height: 20px;
}

QComboBox:hover {
    border: 1px solid #60a5fa;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 28px;
    border-left: 1px solid #334155;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}

QComboBox QAbstractItemView {
    background: #1e293b;
    color: #e2e8f0;
    border: 1px solid #334155;
    border-radius: 6px;
    selection-background-color: #3b82f6;
    selection-color: white;
    outline: none;
    padding: 4px;
}

QComboBox QAbstractItemView::item {
    padding: 8px 12px;
    border-radius: 4px;
    min-height: 24px;
}

QComboBox QAbstractItemView::item:hover {
    background: #334155;
}

QListWidget {
    background: #0f172a;
    color: #e2e8f0;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 4px;
    outline: none;
}

QListWidget::item {
    padding: 8px 12px;
    border-radius: 4px;
    margin: 2px 0px;
}

QListWidget::item:hover {
    background: #1e293b;
}

QListWidget::item:selected {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1d4ed8, stop:1 #2563eb);
    color: white;
}

QScrollArea {
    background: transparent;
    border: none;
}

QScrollBar:vertical {
    background: #0f172a;
    width: 8px;
    border-radius: 4px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #334155;
    min-height: 30px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #475569;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background: #0f172a;
    height: 8px;
    border-radius: 4px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: #334155;
    min-width: 30px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background: #475569;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

QDialogButtonBox QPushButton {
    min-width: 80px;
}

QTimeEdit {
    background: #0f172a;
    color: #e2e8f0;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 14px;
}

QTimeEdit:focus {
    border: 1px solid #60a5fa;
}

QTimeEdit::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid #334155;
}

QFrame {
    border: none;
}
"""

# Acrylic-style overlay for region selection
REGION_SELECTION_STYLE = """
QMainWindow {
    background: transparent;
}
"""

def resize_image(image):
    MAX_PIXELS = 1_800_000
    current_pixels = image.width * image.height
    if current_pixels <= MAX_PIXELS:
        return image
    scale_factor = (MAX_PIXELS / current_pixels) ** 0.5
    new_width = int(image.width * scale_factor)
    new_height = int(image.height * scale_factor)
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


def make_accent_button(text):
    """Create a primary/accent styled button."""
    btn = QPushButton(text)
    btn.setStyleSheet("""
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563eb, stop:1 #1d4ed8);
            color: white;
            border: none;
            border-radius: 6px;
            padding: 8px 20px;
            font-size: 12px;
            font-weight: 700;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3b82f6, stop:1 #2563eb);
        }
        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1d4ed8, stop:1 #1e3a8a);
        }
    """)
    return btn


def make_card_frame():
    """Create a card-like container frame."""
    frame = QFrame()
    frame.setStyleSheet("""
        QFrame {
            background: rgba(30, 41, 59, 0.85);
            border: 1px solid #334155;
            border-radius: 8px;
        }
    """)
    return frame


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


class ModernTitleBar(QWidget):
    """Custom Windows 11-style title bar."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(32)
        self.old_pos = None
        self.initUI()

    def initUI(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(0)

        # App icon / title
        self.title_label = QLabel("AI Backseater")
        self.title_label.setStyleSheet("""
            QLabel {
                color: #e2e8f0;
                font-size: 12px;
                font-weight: 600;
                padding: 0px 8px;
                background: transparent;
            }
        """)
        layout.addWidget(self.title_label)
        layout.addStretch()

        # Minimize button
        self.min_btn = QPushButton("─")
        self.min_btn.setFixedSize(46, 32)
        self.min_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #94a3b8;
                border: none;
                border-radius: 0px;
                font-size: 13px;
                font-weight: 400;
                padding: 0px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.08);
                color: #e2e8f0;
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.04);
            }
        """)
        self.min_btn.clicked.connect(self.parent.showMinimized)
        layout.addWidget(self.min_btn)

        # Maximize button
        self.max_btn = QPushButton("□")
        self.max_btn.setFixedSize(46, 32)
        self.max_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #94a3b8;
                border: none;
                border-radius: 0px;
                font-size: 13px;
                font-weight: 400;
                padding: 0px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.08);
                color: #e2e8f0;
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.04);
            }
        """)
        self.max_btn.clicked.connect(self.toggle_maximize)
        layout.addWidget(self.max_btn)

        # Close button
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(46, 32)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #94a3b8;
                border: none;
                border-radius: 0px;
                font-size: 13px;
                font-weight: 400;
                padding: 0px;
            }
            QPushButton:hover {
                background: #c42b1c;
                color: white;
            }
            QPushButton:pressed {
                background: #a82012;
                color: white;
            }
        """)
        self.close_btn.clicked.connect(self.parent.close_to_tray)
        layout.addWidget(self.close_btn)

        self.setStyleSheet("""
            ModernTitleBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1a1a2e, stop:1 #16213e);
                border-bottom: 1px solid #1e293b;
            }
        """)

    def toggle_maximize(self):
        if self.parent.isMaximized():
            self.parent.showNormal()
            self.max_btn.setText("□")
        else:
            self.parent.showMaximized()
            self.max_btn.setText("❐")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        if self.old_pos is not None:
            if self.parent.isMaximized():
                # Calculate click position as fraction of width
                click_ratio = event.pos().x() / self.width()
                self.parent.showNormal()
                self.max_btn.setText("□")
                # Move window so cursor stays on title bar
                new_x = event.globalPos().x() - int(self.width() * click_ratio)
                self.parent.move(new_x, 0)
            delta = event.globalPos() - self.old_pos
            self.parent.move(self.parent.pos() + delta)
            self.old_pos = event.globalPos()

    def mouseReleaseEvent(self, event):
        self.old_pos = None

    def mouseDoubleClickEvent(self, event):
        self.toggle_maximize()


class MainWindow(QMainWindow):
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
        self.is_selecting_region = False
        self.analysis_paused = False
        self.start_point = None
        self.end_point = None
        self.buttons_visible = True
        self.hide_during_screenshot = True
        self.history_manager = HistoryManager()
        self.timer_start = None
        self.timer_end = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_timer)
        self.timer.start(60000)
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

        self.setWindowTitle("AI Backseater")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setMinimumSize(640, 400)

        # Setup system tray
        self.setup_tray_icon()

        # Start in paused mode - backend may not be available
        self.is_paused = True
        self.pause_resume_btn = None  # Will be set in initUI

        self.initUI()

        # Ensure pause button reflects initial paused state
        self.pause_resume_btn.setText("▶ Resume")
        self.status_label.setText("Paused")
        self.update_text("Application started in paused mode. Press Resume to begin analysis.")

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

        # Restore geometry
        self.restore_geometry()

    def setup_tray_icon(self):
        """Create system tray icon with context menu."""
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setToolTip("AI Backseater")
        
        # Create a simple icon programmatically
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#60a5fa"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(1, 1, 14, 14)
        painter.end()
        self.tray_icon.setIcon(QIcon(pixmap))
        
        # Create tray menu with dark theme
        tray_menu = QMenu()
        tray_menu.setStyleSheet("""
            QMenu {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 24px;
                border-radius: 4px;
                color: #e2e8f0;
                font-size: 12px;
            }
            QMenu::item:selected {
                background: #334155;
                color: white;
            }
            QMenu::separator {
                height: 1px;
                background: #334155;
                margin: 4px 8px;
            }
        """)
        
        show_action = tray_menu.addAction("Show Window")
        show_action.triggered.connect(self.show_from_tray)
        
        pause_action = tray_menu.addAction("Pause/Resume")
        pause_action.triggered.connect(self.toggle_pause_resume)
        
        tray_menu.addSeparator()
        
        quit_action = tray_menu.addAction("Quit")
        quit_action.triggered.connect(self.quit_application)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def on_tray_activated(self, reason):
        """Handle tray icon activation."""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_from_tray()

    def show_from_tray(self):
        """Restore window from tray."""
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def close_to_tray(self):
        """Minimize to tray instead of closing."""
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
            self.tray_icon.showMessage(
                "AI Backseater",
                "Application minimized to tray. Double-click to restore.",
                QSystemTrayIcon.Information,
                2000
            )
        else:
            self.quit_application()

    def quit_application(self):
        """Properly quit the application."""
        self.save_geometry()
        self.analysis_worker.stop()
        self.analysis_thread.quit()
        self.analysis_thread.wait()
        self.speech_manager.stop()
        self.web_advice_manager.stop()
        QApplication.quit()

    def save_geometry(self):
        """Save window geometry to settings file."""
        settings = {
            "x": self.x(),
            "y": self.y(),
            "width": self.width(),
            "height": self.height(),
            "maximized": self.isMaximized()
        }
        try:
            with open("window_settings.json", "w") as f:
                json.dump(settings, f)
        except Exception:
            pass

    def restore_geometry(self):
        """Restore window geometry from settings file."""
        try:
            if os.path.exists("window_settings.json"):
                with open("window_settings.json", "r") as f:
                    settings = json.load(f)
                self.setGeometry(
                    settings.get("x", 100),
                    settings.get("y", 100),
                    settings.get("width", 900),
                    settings.get("height", 700)
                )
                if settings.get("maximized", False):
                    self.showMaximized()
        except Exception:
            self.resize(900, 700)

    def initUI(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Custom title bar
        self.title_bar = ModernTitleBar(self)
        main_layout.addWidget(self.title_bar)

        # Content area
        content_widget = QWidget()
        content_widget.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1e1e2e, stop:1 #181825);
            }
        """)
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(16, 12, 16, 12)
        content_layout.setSpacing(12)

        # Status bar / info area
        status_frame = QFrame()
        status_frame.setStyleSheet("""
            QFrame {
                background: rgba(30, 41, 59, 0.6);
                border: 1px solid #334155;
                border-radius: 8px;
            }
        """)
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(12, 8, 12, 8)

        status_icon = QLabel("●")
        status_icon.setStyleSheet("color: #22c55e; font-size: 10px; font-weight: bold; background: transparent;")
        status_layout.addWidget(status_icon)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 500; background: transparent;")
        status_layout.addWidget(self.status_label)

        status_layout.addStretch()

        self.region_label = QLabel("No region selected")
        self.region_label.setStyleSheet("color: #64748b; font-size: 11px; background: transparent;")
        status_layout.addWidget(self.region_label)

        content_layout.addWidget(status_frame)

        # Analysis output area
        output_frame = QFrame()
        output_frame.setStyleSheet("""
            QFrame {
                background: rgba(15, 23, 42, 0.85);
                border: 1px solid #334155;
                border-radius: 8px;
            }
        """)
        output_layout = QVBoxLayout(output_frame)
        output_layout.setContentsMargins(12, 12, 12, 12)

        output_header = QLabel("Analysis Output")
        output_header.setStyleSheet("""
            QLabel {
                color: #94a3b8;
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 1px;
                background: transparent;
                padding: 0px;
            }
        """)
        output_layout.addWidget(output_header)

        self.label = QLabel(self)
        self.label.setStyleSheet("""
            QLabel {
                color: #e2e8f0;
                background: transparent;
                padding: 8px 0px;
                font-size: 13px;
                line-height: 1.5;
            }
        """)
        self.label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.label.setFont(QFont('Segoe UI', 13))
        self.label.setWordWrap(True)
        output_layout.addWidget(self.label)

        content_layout.addWidget(output_frame, 1)

        # Toolbar / button area
        toolbar_frame = QFrame()
        toolbar_frame.setStyleSheet("""
            QFrame {
                background: rgba(30, 41, 59, 0.6);
                border: 1px solid #334155;
                border-radius: 8px;
            }
        """)
        toolbar_layout = QVBoxLayout(toolbar_frame)
        toolbar_layout.setContentsMargins(12, 10, 12, 10)
        toolbar_layout.setSpacing(6)

        # Row 1: Core controls
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        select_region_btn = QPushButton("■ Select Region")
        select_region_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563eb, stop:1 #1d4ed8);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3b82f6, stop:1 #2563eb);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1d4ed8, stop:1 #1e3a8a);
            }
        """)
        select_region_btn.clicked.connect(self.select_region)
        row1.addWidget(select_region_btn)

        self.pause_resume_btn = QPushButton("⏸ Pause")
        self.pause_resume_btn.clicked.connect(self.toggle_pause_resume)
        row1.addWidget(self.pause_resume_btn)

        char_btn = QPushButton("Character")
        char_btn.clicked.connect(self.show_prompt_dialog)
        row1.addWidget(char_btn)

        set_timer_btn = QPushButton("⏱ Timer")
        set_timer_btn.clicked.connect(self.show_timer_dialog)
        row1.addWidget(set_timer_btn)

        row1.addStretch()

        toolbar_layout.addLayout(row1)

        # Row 2: Settings and utilities
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        ooba_btn = QPushButton("LLM Settings")
        ooba_btn.clicked.connect(self.show_oobabooga_settings_dialog)
        row2.addWidget(ooba_btn)

        interval_btn = QPushButton("Interval")
        interval_btn.clicked.connect(self.show_interval_dialog)
        row2.addWidget(interval_btn)

        tts_btn = QPushButton("TTS")
        tts_btn.clicked.connect(self.show_tts_settings_dialog)
        row2.addWidget(tts_btn)

        web_btn = QPushButton("Web Advice")
        web_btn.clicked.connect(self.show_web_advice_settings_dialog)
        row2.addWidget(web_btn)

        alert_btn = QPushButton("Alert")
        alert_btn.clicked.connect(self.set_alert_prompt)
        row2.addWidget(alert_btn)

        history_btn = QPushButton("History")
        history_btn.clicked.connect(self.show_history_dialog)
        row2.addWidget(history_btn)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_results)
        row2.addWidget(save_btn)

        hide_btn = QPushButton("Hide Capture")
        hide_btn.clicked.connect(self.toggle_hide_during_screenshot)
        row2.addWidget(hide_btn)

        toolbar_layout.addLayout(row2)

        content_layout.addWidget(toolbar_frame)

        main_layout.addWidget(content_widget, 1)

        # Enable resizing from edges
        self.resize_margin = 4
        self.dragging_edge = None

        self.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Check if we're on an edge for resizing
            pos = event.pos()
            rect = self.rect()
            margin = self.resize_margin
            
            on_left = pos.x() <= margin
            on_right = pos.x() >= rect.width() - margin
            on_top = pos.y() <= margin
            on_bottom = pos.y() >= rect.height() - margin
            
            if on_left and on_top:
                self.dragging_edge = "topleft"
            elif on_right and on_top:
                self.dragging_edge = "topright"
            elif on_left and on_bottom:
                self.dragging_edge = "bottomleft"
            elif on_right and on_bottom:
                self.dragging_edge = "bottomright"
            elif on_left:
                self.dragging_edge = "left"
            elif on_right:
                self.dragging_edge = "right"
            elif on_top:
                self.dragging_edge = "top"
            elif on_bottom:
                self.dragging_edge = "bottom"
            else:
                self.dragging_edge = None
            
            if self.dragging_edge:
                self.drag_start_pos = event.globalPos()
                self.drag_start_rect = self.geometry()
            elif event.button() == Qt.RightButton:
                self.show_context_menu(event.pos())

    def mouseMoveEvent(self, event):
        if self.dragging_edge and event.buttons() & Qt.LeftButton:
            delta = event.globalPos() - self.drag_start_pos
            rect = QRect(self.drag_start_rect)
            
            if "left" in self.dragging_edge:
                rect.setLeft(rect.left() + delta.x())
            if "right" in self.dragging_edge:
                rect.setRight(rect.right() + delta.x())
            if "top" in self.dragging_edge:
                rect.setTop(rect.top() + delta.y())
            if "bottom" in self.dragging_edge:
                rect.setBottom(rect.bottom() + delta.y())
            
            # Enforce minimum size
            if rect.width() < self.minimumWidth():
                if "left" in self.dragging_edge:
                    rect.setLeft(rect.right() - self.minimumWidth())
                else:
                    rect.setRight(rect.left() + self.minimumWidth())
            if rect.height() < self.minimumHeight():
                if "top" in self.dragging_edge:
                    rect.setTop(rect.bottom() - self.minimumHeight())
                else:
                    rect.setBottom(rect.top() + self.minimumHeight())
            
            self.setGeometry(rect)
        else:
            # Update cursor based on position
            pos = event.pos()
            rect = self.rect()
            margin = self.resize_margin
            
            on_left = pos.x() <= margin
            on_right = pos.x() >= rect.width() - margin
            on_top = pos.y() <= margin
            on_bottom = pos.y() >= rect.height() - margin
            
            if on_left and on_top:
                self.setCursor(QCursor(Qt.SizeFDiagCursor))
            elif on_right and on_top:
                self.setCursor(QCursor(Qt.SizeBDiagCursor))
            elif on_left and on_bottom:
                self.setCursor(QCursor(Qt.SizeBDiagCursor))
            elif on_right and on_bottom:
                self.setCursor(QCursor(Qt.SizeFDiagCursor))
            elif on_left or on_right:
                self.setCursor(QCursor(Qt.SizeHorCursor))
            elif on_top or on_bottom:
                self.setCursor(QCursor(Qt.SizeVerCursor))
            else:
                self.setCursor(QCursor(Qt.ArrowCursor))

    def mouseReleaseEvent(self, event):
        self.dragging_edge = None
        self.drag_start_pos = None
        self.drag_start_rect = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Only respond to double clicks on the title bar area
            if event.pos().y() <= self.title_bar.height():
                self.title_bar.toggle_maximize()

    def closeEvent(self, event):
        """Override close event to minimize to tray."""
        event.ignore()
        self.close_to_tray()

    def update_text(self, text):
        self.label.setText(text)
        self.analysis_results.append(text)
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
        dialog.setMinimumSize(640, 480)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header = QLabel("Analysis History")
        header.setStyleSheet("""
            QLabel {
                color: #f1f5f9;
                font-size: 18px;
                font-weight: 700;
                background: transparent;
                padding: 0px;
            }
        """)
        layout.addWidget(header)

        # Search box
        search_box = QLineEdit(dialog)
        search_box.setPlaceholderText("🔍 Search history...")
        search_box.setStyleSheet("""
            QLineEdit {
                background: #0f172a;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #60a5fa;
            }
        """)
        layout.addWidget(search_box)

        # List widget
        list_widget = QListWidget(dialog)
        list_widget.setStyleSheet("""
            QListWidget {
                background: #0f172a;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 6px;
                outline: none;
            }
            QListWidget::item {
                padding: 10px 14px;
                border-radius: 6px;
                margin: 2px 0px;
                border-bottom: 1px solid #1e293b;
            }
            QListWidget::item:hover {
                background: #1e293b;
            }
            QListWidget::item:selected {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1d4ed8, stop:1 #2563eb);
                color: white;
            }
        """)
        layout.addWidget(list_widget)

        def update_list(query=''):
            list_widget.clear()
            if query:
                history = self.history_manager.search_history(query)
            else:
                history = self.history_manager.get_history()
            for item in history:
                timestamp_str = item[1][:19]  # Trim to seconds
                text_preview = item[2][:60].replace('\n', ' ')
                list_widget.addItem(f"{timestamp_str}  —  {text_preview}...")

        def open_analysis(item):
            selected_text = item.text()
            parts = selected_text.split("  —  ")
            if parts:
                timestamp = parts[0].strip()
                full_analysis = self.history_manager.get_analysis_by_timestamp(timestamp)
                if full_analysis:
                    self.show_analysis_detail(full_analysis)

        list_widget.itemClicked.connect(open_analysis)
        search_box.textChanged.connect(update_list)
        update_list()

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        close_btn.setStyleSheet("""
            QPushButton {
                background: #334155;
                color: #e2e8f0;
                border: 1px solid #475569;
                border-radius: 6px;
                padding: 8px 24px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #3b4f6f;
                border: 1px solid #60a5fa;
            }
        """)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

        dialog.exec_()

    def show_analysis_detail(self, analysis):
        detail_dialog = QDialog(self)
        detail_dialog.setWindowTitle(f"Analysis — {analysis[1][:19]}")
        detail_dialog.setMinimumSize(700, 500)
        detail_dialog.setWindowFlags(detail_dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(detail_dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Timestamp
        ts_label = QLabel(f"📅 {analysis[1][:19]}")
        ts_label.setStyleSheet("""
            QLabel {
                color: #64748b;
                font-size: 12px;
                background: transparent;
                padding: 0px;
            }
        """)
        layout.addWidget(ts_label)

        # Prompt section
        prompt_frame = QFrame()
        prompt_frame.setStyleSheet("""
            QFrame {
                background: rgba(30, 41, 59, 0.5);
                border: 1px solid #334155;
                border-radius: 8px;
            }
        """)
        prompt_layout = QVBoxLayout(prompt_frame)
        prompt_layout.setContentsMargins(12, 10, 12, 10)
        
        prompt_header = QLabel("Prompt")
        prompt_header.setStyleSheet("""
            QLabel {
                color: #94a3b8;
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 1px;
                background: transparent;
                padding: 0px;
            }
        """)
        prompt_layout.addWidget(prompt_header)
        
        prompt_text = QLabel(analysis[3])
        prompt_text.setStyleSheet("color: #cbd5e1; font-size: 12px; background: transparent; padding: 0px;")
        prompt_text.setWordWrap(True)
        prompt_layout.addWidget(prompt_text)
        
        layout.addWidget(prompt_frame)

        # Analysis text
        analysis_frame = QFrame()
        analysis_frame.setStyleSheet("""
            QFrame {
                background: rgba(15, 23, 42, 0.85);
                border: 1px solid #334155;
                border-radius: 8px;
            }
        """)
        analysis_layout = QVBoxLayout(analysis_frame)
        analysis_layout.setContentsMargins(12, 10, 12, 10)
        
        analysis_header = QLabel("Analysis")
        analysis_header.setStyleSheet("""
            QLabel {
                color: #94a3b8;
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 1px;
                background: transparent;
                padding: 0px;
            }
        """)
        analysis_layout.addWidget(analysis_header)
        
        analysis_text = QTextEdit()
        analysis_text.setPlainText(analysis[2])
        analysis_text.setReadOnly(True)
        analysis_text.setStyleSheet("""
            QTextEdit {
                background: transparent;
                color: #e2e8f0;
                border: none;
                font-size: 13px;
                padding: 0px;
            }
        """)
        analysis_layout.addWidget(analysis_text)
        
        layout.addWidget(analysis_frame, 1)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(detail_dialog.accept)
        close_btn.setStyleSheet("""
            QPushButton {
                background: #334155;
                color: #e2e8f0;
                border: 1px solid #475569;
                border-radius: 6px;
                padding: 8px 24px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #3b4f6f;
                border: 1px solid #60a5fa;
            }
        """)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

        detail_dialog.exec_()

    def show_export_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Export History")
        dialog.setFixedSize(320, 180)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        header = QLabel("Export Analysis History")
        header.setStyleSheet("""
            QLabel {
                color: #f1f5f9;
                font-size: 16px;
                font-weight: 700;
                background: transparent;
                padding: 0px;
            }
        """)
        layout.addWidget(header)

        desc = QLabel("Choose a format to export your analysis history.")
        desc.setStyleSheet("color: #64748b; font-size: 12px; background: transparent; padding: 0px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        json_btn = QPushButton("Export as JSON")
        csv_btn = QPushButton("Export as CSV")

        btn_layout.addWidget(json_btn)
        btn_layout.addWidget(csv_btn)
        layout.addLayout(btn_layout)

        def export_json():
            filename, _ = QFileDialog.getSaveFileName(self, "Save JSON", "", "JSON Files (*.json)")
            if filename:
                self.history_manager.export_to_json(filename)
                QMessageBox.information(self, "Export Successful", f"Data exported to {filename}")
                dialog.accept()

        def export_csv():
            filename, _ = QFileDialog.getSaveFileName(self, "Save CSV", "", "CSV Files (*.csv)")
            if filename:
                self.history_manager.export_to_csv(filename)
                QMessageBox.information(self, "Export Successful", f"Data exported to {filename}")
                dialog.accept()

        json_btn.clicked.connect(export_json)
        csv_btn.clicked.connect(export_csv)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        layout.addWidget(cancel_btn)

        dialog.exec_()
    
    @pyqtSlot(str, str)
    def trigger_alert(self, alert_prompt, analysis_text):
        QTimer.singleShot(0, lambda: self._show_alert(alert_prompt, analysis_text))

    def _show_alert(self, alert_prompt, analysis_text):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Alert Condition Met")
        msg.setText(f"The condition was detected:")
        msg.setInformativeText(f"\"{alert_prompt}\"")
        msg.setDetailedText(analysis_text)
        
        # Style the message box
        msg.setStyleSheet("""
            QMessageBox {
                background: #1e1e2e;
            }
            QLabel {
                color: #e2e8f0;
                font-size: 13px;
                background: transparent;
            }
            QPushButton {
                background: #334155;
                color: #e2e8f0;
                border: 1px solid #475569;
                border-radius: 6px;
                padding: 7px 16px;
                font-size: 12px;
                font-weight: 600;
                min-width: 80px;
            }
            QPushButton:hover {
                background: #3b4f6f;
                border: 1px solid #60a5fa;
            }
            QTextEdit {
                background: #0f172a;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 6px;
                font-size: 12px;
            }
        """)
        msg.exec_()

    @pyqtSlot(str)
    def handle_error(self, error_message):
        logging.error(f"Error in analysis thread: {error_message}")
        # Auto-pause on backend errors to prevent spam
        if "Unable to analyze image" in error_message or "Error communicating" in error_message or "Connection" in error_message:
            if not self.is_paused:
                self.toggle_pause_resume()
            self.status_label.setText("Backend offline - paused")
            self.update_text("Backend is not responding. Application paused. Press Resume to try again.")
        else:
            self.update_text(f"An error occurred: {error_message}")

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def toggle_pause_resume(self):
        self.is_paused = not self.is_paused
        button_text = "▶ Resume" if self.is_paused else "⏸ Pause"
        self.pause_resume_btn.setText(button_text)
        status = "paused" if self.is_paused else "resumed"
        self.status_label.setText(status.capitalize())
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

    def show_context_menu(self, pos):
        context_menu = QMenu(self)
        context_menu.setStyleSheet("""
            QMenu {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 24px;
                border-radius: 4px;
                color: #e2e8f0;
                font-size: 12px;
            }
            QMenu::item:selected {
                background: #334155;
                color: white;
            }
            QMenu::separator {
                height: 1px;
                background: #334155;
                margin: 4px 8px;
            }
        """)
        
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
        context_menu.addSeparator()
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
            self.quit_application()

    def toggle_buttons_visibility(self):
        self.buttons_visible = not self.buttons_visible
        # For the new layout, we hide/show the toolbar frames
        for widget in self.findChildren(QFrame):
            if widget.parent() is self.centralWidget() or widget.parent().parent() is self.centralWidget():
                if "rgba(30, 41, 59" in widget.styleSheet():
                    widget.setVisible(self.buttons_visible)

    def resize_overlay(self):
        new_width, ok1 = QInputDialog.getInt(self, 'Resize Window', 'Enter new width:', self.width(), 400, 2000)
        if ok1:
            new_height, ok2 = QInputDialog.getInt(self, 'Resize Window', 'Enter new height:', self.height(), 300, 2000)
            if ok2:
                self.resize(new_width, new_height)
                self.update_text(f"Window resized to {new_width}x{new_height}")

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
        self.select_window.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.select_window.setGeometry(screen.geometry())
        self.select_window.setAttribute(Qt.WA_TranslucentBackground)
        self.select_window.setStyleSheet(REGION_SELECTION_STYLE)
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
            self.region_label.setText(f"Region: {self.capture_region.width()}×{self.capture_region.height()}")
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
            painter.setPen(QPen(QColor("#60a5fa"), 2, Qt.SolidLine))
            painter.setBrush(QColor(96, 165, 250, 40))
            painter.drawRect(QRect(self.start_point, self.end_point).normalized())
        
        # Draw instructions with modern style
        painter.setPen(Qt.white)
        painter.setFont(QFont('Segoe UI', 13))
        
        # Background for text
        text_rect = QRect(10, 10, 400, 30)
        painter.fillRect(text_rect, QColor(0, 0, 0, 160))
        painter.drawText(10, 30, "Click and drag to select a region. Press Esc to cancel.")

    def update_analysis_prompt(self, new_prompt):
        self.analysis_prompt = new_prompt

    def show_prompt_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Character & Prompt Settings")
        dialog.setMinimumSize(700, 520)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QLabel("Character & Prompt")
        header.setStyleSheet("""
            QLabel {
                color: #f1f5f9;
                font-size: 18px;
                font-weight: 700;
                background: transparent;
                padding: 0px;
            }
        """)
        layout.addWidget(header)

        # Preset selection
        preset_label = QLabel("Character Preset")
        preset_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600; background: transparent; padding: 0px;")
        layout.addWidget(preset_label)
        
        preset_combo = QComboBox(dialog)
        preset_combo.addItem("Custom")
        for preset_name in CHARACTER_PRESETS:
            preset_combo.addItem(preset_name)
        preset_combo.setCurrentText(
            self.character_preset_name if self.character_preset_name in CHARACTER_PRESETS else "Custom"
        )
        layout.addWidget(preset_combo)

        # Character prompt section
        char_label = QLabel("Character Prompt")
        char_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600; background: transparent; padding: 0px;")
        layout.addWidget(char_label)

        character_text = QTextEdit(dialog)
        character_text.setPlainText(self.character_prompt)
        character_text.setMinimumHeight(100)
        layout.addWidget(character_text)

        # Analysis prompt section
        analysis_label = QLabel("Current Screenshot Prompt")
        analysis_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600; background: transparent; padding: 0px;")
        layout.addWidget(analysis_label)

        analysis_text = QTextEdit(dialog)
        analysis_text.setPlainText(self.analysis_prompt)
        analysis_text.setMinimumHeight(100)
        layout.addWidget(analysis_text)

        # Memory clear button
        clear_memory_button = QPushButton("Clear Conversation Memory")
        clear_memory_button.clicked.connect(lambda: self.clear_conversation_memory(dialog))
        layout.addWidget(clear_memory_button)

        def apply_preset(preset_name):
            if preset_name == "Custom":
                return
            preset = CHARACTER_PRESETS[preset_name]
            character_text.setPlainText(preset["character"])
            analysis_text.setPlainText(preset["analysis"])

        preset_combo.currentTextChanged.connect(apply_preset)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton("Apply")
        ok_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563eb, stop:1 #1d4ed8);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 24px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3b82f6, stop:1 #2563eb);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1d4ed8, stop:1 #1e3a8a);
            }
        """)
        ok_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(ok_btn)
        
        layout.addLayout(button_layout)

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
        dialog.setWindowTitle("Text-to-Speech Settings")
        dialog.setMinimumSize(450, 350)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QLabel("Text-to-Speech")
        header.setStyleSheet("""
            QLabel {
                color: #f1f5f9;
                font-size: 18px;
                font-weight: 700;
                background: transparent;
                padding: 0px;
            }
        """)
        layout.addWidget(header)

        # Enabled
        enabled_label = QLabel("Voice Output")
        enabled_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600; background: transparent; padding: 0px;")
        layout.addWidget(enabled_label)
        
        enabled_combo = QComboBox(dialog)
        enabled_combo.addItems(["Enabled", "Disabled"])
        enabled_combo.setCurrentText("Enabled" if self.tts_enabled else "Disabled")
        layout.addWidget(enabled_combo)

        # Language code
        lang_label = QLabel("Kokoro Language Code")
        lang_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600; background: transparent; padding: 0px;")
        layout.addWidget(lang_label)
        
        lang_input = QLineEdit(self.tts_lang_code)
        layout.addWidget(lang_input)

        # Voice
        voice_label = QLabel("Kokoro Voice")
        voice_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600; background: transparent; padding: 0px;")
        layout.addWidget(voice_label)
        
        voice_input = QLineEdit(self.tts_voice)
        layout.addWidget(voice_input)

        # Speed
        speed_label = QLabel("Speed (0.5–2.0)")
        speed_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600; background: transparent; padding: 0px;")
        layout.addWidget(speed_label)
        
        speed_input = QLineEdit(str(self.tts_speed))
        layout.addWidget(speed_input)

        # Test button
        test_button = QPushButton("🔊 Test Voice")
        test_button.clicked.connect(lambda: self._test_tts(enabled_combo, lang_input, voice_input, speed_input))
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

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        if dialog.exec_() == QDialog.Accepted:
            apply_tts_settings()
            status = "enabled" if self.tts_enabled else "disabled"
            self.update_text(f"TTS {status}: {self.tts_voice}")

    def _test_tts(self, enabled_combo, lang_input, voice_input, speed_input):
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
        self.speech_manager.speak("Hmph. Fine, I can talk now. Try not to embarrass yourself too badly.")

    def show_web_advice_settings_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Web Advice Settings")
        dialog.setMinimumSize(550, 400)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QLabel("Web Advice")
        header.setStyleSheet("""
            QLabel {
                color: #f1f5f9;
                font-size: 18px;
                font-weight: 700;
                background: transparent;
                padding: 0px;
            }
        """)
        layout.addWidget(header)

        # Enabled
        enabled_label = QLabel("Periodic Web Advice")
        enabled_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600; background: transparent; padding: 0px;")
        layout.addWidget(enabled_label)
        
        enabled_combo = QComboBox(dialog)
        enabled_combo.addItems(["Disabled", "Enabled"])
        enabled_combo.setCurrentText("Enabled" if self.web_advice_enabled else "Disabled")
        layout.addWidget(enabled_combo)

        # Query
        query_label = QLabel("Search Query / Game / URL")
        query_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600; background: transparent; padding: 0px;")
        layout.addWidget(query_label)
        
        query_input = QLineEdit(self.web_advice_query)
        layout.addWidget(query_input)

        # Interval
        interval_label = QLabel("Fetch Interval (minutes)")
        interval_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600; background: transparent; padding: 0px;")
        layout.addWidget(interval_label)
        
        interval_input = QLineEdit(str(self.web_advice_interval_minutes))
        layout.addWidget(interval_input)

        # Max snippets
        snippets_label = QLabel("Max Snippets Kept")
        snippets_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600; background: transparent; padding: 0px;")
        layout.addWidget(snippets_label)
        
        snippets_input = QLineEdit(str(self.web_advice_max_snippets))
        layout.addWidget(snippets_input)

        # Preview
        preview_label = QLabel("Current Notes")
        preview_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600; background: transparent; padding: 0px;")
        layout.addWidget(preview_label)
        
        preview = QTextEdit(dialog)
        preview.setReadOnly(True)
        preview.setPlainText("\n".join(self.web_advice_notes) if self.web_advice_notes else "No web advice fetched yet.")
        preview.setMaximumHeight(80)
        layout.addWidget(preview)

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

        button_row = QHBoxLayout()
        fetch_now_button = QPushButton("Fetch Now")
        fetch_now_button.clicked.connect(lambda: apply_web_advice_settings(fetch_now=True))
        button_row.addWidget(fetch_now_button)
        button_row.addStretch()
        layout.addLayout(button_row)

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
        # Create a styled input dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Set Alert Condition")
        dialog.setFixedSize(420, 200)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QLabel("Alert Condition")
        header.setStyleSheet("""
            QLabel {
                color: #f1f5f9;
                font-size: 16px;
                font-weight: 700;
                background: transparent;
                padding: 0px;
            }
        """)
        layout.addWidget(header)

        desc = QLabel("Enter a condition to monitor for (e.g., \"Can you see birds?\")")
        desc.setStyleSheet("color: #64748b; font-size: 12px; background: transparent; padding: 0px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        input_field = QLineEdit(self.alert_prompt)
        input_field.setPlaceholderText("Type alert condition here...")
        layout.addWidget(input_field)

        btn_layout = QHBoxLayout()
        clear_btn = QPushButton("Clear Alert")
        clear_btn.clicked.connect(lambda: [input_field.clear(), dialog.accept()])
        btn_layout.addWidget(clear_btn)
        
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton("Set Alert")
        ok_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563eb, stop:1 #1d4ed8);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3b82f6, stop:1 #2563eb);
            }
        """)
        ok_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(ok_btn)
        
        layout.addLayout(btn_layout)

        if dialog.exec_() == QDialog.Accepted:
            prompt = input_field.text().strip()
            if prompt:
                self.alert_prompt = prompt
                self.alert_active = True
                self.update_text(f"Alert set for condition: {self.alert_prompt}")
            else:
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
        dialog.setFixedSize(350, 250)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QLabel("Analysis Timer")
        header.setStyleSheet("""
            QLabel {
                color: #f1f5f9;
                font-size: 16px;
                font-weight: 700;
                background: transparent;
                padding: 0px;
            }
        """)
        layout.addWidget(header)

        start_label = QLabel("Start Time")
        start_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600; background: transparent; padding: 0px;")
        layout.addWidget(start_label)
        
        start_time_edit = QTimeEdit(dialog)
        start_time_edit.setDisplayFormat("HH:mm")
        layout.addWidget(start_time_edit)

        end_label = QLabel("End Time")
        end_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600; background: transparent; padding: 0px;")
        layout.addWidget(end_label)
        
        end_time_edit = QTimeEdit(dialog)
        end_time_edit.setDisplayFormat("HH:mm")
        layout.addWidget(end_time_edit)

        btn_layout = QHBoxLayout()
        clear_btn = QPushButton("Clear Timer")
        clear_btn.clicked.connect(lambda: [setattr(self, 'timer_start', None), setattr(self, 'timer_end', None), self.update_text("Timer cleared"), self.check_timer(), dialog.accept()])
        btn_layout.addWidget(clear_btn)
        
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton("Set Timer")
        ok_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563eb, stop:1 #1d4ed8);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3b82f6, stop:1 #2563eb);
            }
        """)
        ok_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(ok_btn)
        
        layout.addLayout(btn_layout)

        if dialog.exec_() == QDialog.Accepted:
            self.timer_start = start_time_edit.time().toPyTime()
            self.timer_end = end_time_edit.time().toPyTime()
            self.update_text(f"Timer set: {self.timer_start.strftime('%H:%M')} - {self.timer_end.strftime('%H:%M')}")
            self.check_timer()

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
            self.hide()
        QApplication.processEvents()

        try:
            if self.capture_region and not self.is_selecting_region:
                screen = QApplication.primaryScreen()
                screen_geometry = screen.geometry()
                left = self.capture_region.left() + screen_geometry.left()
                top = self.capture_region.top() + screen_geometry.top()
                right = self.capture_region.right() + screen_geometry.left()
                bottom = self.capture_region.bottom() + screen_geometry.top()

                img = ImageGrab.grab(bbox=(left, top, right, bottom))
                logging.info(f"Screenshot taken of selected region: {left},{top},{right},{bottom}")
            else:
                img = ImageGrab.grab()
                logging.info("Full screen screenshot taken")

            if self.hide_during_screenshot:
                self.show()

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
                self.show()
            self.analysis_worker.set_captured_image(self.current_image)

    def show_oobabooga_settings_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("LLM / Oobabooga Settings")
        dialog.setMinimumSize(500, 380)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QLabel("LLM Settings")
        header.setStyleSheet("""
            QLabel {
                color: #f1f5f9;
                font-size: 18px;
                font-weight: 700;
                background: transparent;
                padding: 0px;
            }
        """)
        layout.addWidget(header)

        # URL
        url_label = QLabel("Oobabooga OpenAI URL")
        url_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600; background: transparent; padding: 0px;")
        layout.addWidget(url_label)
        
        oobabooga_url_input = QLineEdit(self.oobabooga_url)
        layout.addWidget(oobabooga_url_input)

        # Model
        model_label = QLabel("Model")
        model_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600; background: transparent; padding: 0px;")
        layout.addWidget(model_label)
        
        oobabooga_model_input = QLineEdit(self.oobabooga_model)
        layout.addWidget(oobabooga_model_input)

        # Template
        template_label = QLabel("Instruction Template")
        template_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600; background: transparent; padding: 0px;")
        layout.addWidget(template_label)
        
        instruction_template_input = QLineEdit(self.instruction_template)
        layout.addWidget(instruction_template_input)

        # Context size
        context_label = QLabel("Context Size (tokens)")
        context_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600; background: transparent; padding: 0px;")
        layout.addWidget(context_label)
        
        context_input = QLineEdit(str(self.context_size_tokens))
        layout.addWidget(context_input)

        # Max response
        response_label = QLabel("Max Response (tokens)")
        response_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600; background: transparent; padding: 0px;")
        layout.addWidget(response_label)
        
        max_response_input = QLineEdit(str(self.max_response_tokens))
        layout.addWidget(max_response_input)

        # Detect button
        detect_context_button = QPushButton("🔍 Detect Context Size")
        detect_context_button.clicked.connect(lambda: self._detect_context_size(
            oobabooga_url_input, oobabooga_model_input, instruction_template_input, context_input))
        layout.addWidget(detect_context_button)

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

    def _detect_context_size(self, url_input, model_input, template_input, context_input):
        client = OobaboogaClient()
        client.oobabooga_url = url_input.text().strip() or OOBA_OPENAI_URL
        client.oobabooga_model = model_input.text().strip() or "local-model"
        client.instruction_template = template_input.text().strip() or DEFAULT_INSTRUCTION_TEMPLATE
        detected = client.infer_context_size()
        if detected:
            context_input.setText(str(detected))
            QMessageBox.information(self, "Context Size Detected", f"Detected context size: {detected} tokens")
        else:
            QMessageBox.warning(self, "Context Size Not Found", "Could not detect context size from Oobabooga. Please set it manually.")


def main():
    app = QApplication(sys.argv)
    
    # Apply Windows 11 theme globally
    app.setStyle('Fusion')
    app.setStyleSheet(WINDOWS_11_STYLESHEET)
    
    # Set font
    font = QFont('Segoe UI', 10)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)
    
    main_window = MainWindow()
    main_window.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()