# AI-Backseater

An AI-powered game companion that watches your screen, analyzes gameplay in real-time, and provides voice-enabled commentary through a modern Windows 11-style application.

Powered by an Oobabooga/OpenAI-compatible vision endpoint, the app captures screenshots of a selected region or the full screen and analyzes them using AI, with a configurable character persona, voice output, and optional web-sourced game tips.

> Built on the shoulders of [PasiKoodaa/Screen-Analysis-Overlay](https://github.com/PasiKoodaa/Screen-Analysis-Overlay)

---

## ✨ Features

### Core
- **Real-time screen analysis** — captures screenshots on a configurable interval and sends them to an AI vision model
- **Character-driven AI** — the assistant responds with a defined personality (e.g., "Bratty Coach") using custom system prompts
- **Rolling conversation memory** — the last N exchanges are kept as context; older entries are dropped when token budget is exceeded
- **Voice output** — local Kokoro TTS reads analysis results aloud with configurable voice, language, and speed
- **Alert conditions** — define a condition (e.g., "Can you see an enemy?"); the app will notify you when it's detected

### Modern Windows 11 UI
- **Native window management** — customizable title bar with minimize, maximize (drag to restore), and close-to-tray
- **System tray integration** — minimizes to tray on close; double-click the tray icon to restore, or use the tray's context menu
- **Dark acrylic theme** — gradient background, card-based layout, rounded corners, and a consistent blue-accent palette
- **Edge resizing** — drag any window edge or corner to resize, with smart cursor feedback
- **Geometry persistence** — window position, size, and maximized state are saved between sessions

### History & Data
- **SQLite history** — every analysis is saved with timestamp and prompt for later review
- **Search & browse** — full-text search across all saved analyses
- **Detail viewer** — click any history entry to see the full prompt and analysis text in a clean detail dialog
- **Export** — export your analysis history to JSON or CSV

### Web Advice
- **Periodic game tips** — optionally fetch web snippets (DuckDuckGo or direct URL) on a configurable schedule
- **Context-aware** — the latest snippets are injected into the LLM context when relevant to the current screenshot

### Capture
- **Region or full-screen** — select any rectangle on screen, or capture the entire display
- **Smart hiding** — the app window auto-hides during screenshot capture so it never appears in its own screenshots
- **Image resizing** — images exceeding 1.8M pixels are automatically resized while keeping aspect ratio
- **Scheduled analysis timer** — set a time window (start/end) to automatically pause/resume analysis

---

## 🖼️ Screenshots

| Area | Description |
|------|-------------|
| **Main Window** | Dark card-based layout with status bar, analysis output panel, and toolbar (Region Select, Pause/Resume, Character, Timer, LLM Settings, TTS, Web Advice, Alert, History, Save, Hide Capture) |
| **System Tray** | Dark-themed tray menu with Show Window, Pause/Resume, and Quit |
| **Dialogs** | All settings dialogs (LLM, TTS, Web Advice, Character, History, Alert, Timer, Export) use consistent modern styling |

---

## ⚙️ Requirements

- **Python** 3.10+
- **PyQt5** — UI framework
- **Pillow** — image handling
- **requests** — HTTP client for Oobabooga and web advice
- **Kokoro TTS** — local text-to-speech engine
- **numpy** — audio processing
- **Oobabooga** (text-generation-webui) with a vision-capable model and OpenAI-compatible API enabled

> On Windows, if the selected Kokoro voice requires it, install `espeak-ng` separately.

---

## 📦 Installation

### Automatic (recommended)
Simply double-click **`setup.bat`** — it will:
1. Check that Python 3.10+ is installed
2. Create a virtual environment (`venv/`)
3. Upgrade pip
4. Install all dependencies from `requirements.txt`
5. Check for the optional Kokoro development checkout

After setup completes, double-click **`launch.bat`** to start the app. On first launch, `launch.bat` automatically runs `setup.bat` if the environment isn't ready yet.

### Manual
```bash
# 1. Clone the repository
git clone https://github.com/githubdood21/AI-Backseater.git
cd AI-Backseater

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) Clone Kokoro for a development checkout
git clone https://github.com/hexgrad/kokoro.git
```

---

## 🚀 Usage

### Starting the app
**Simplest:** double-click **`launch.bat`** — it auto-activates the virtual environment and runs the app. If the virtual environment doesn't exist yet, it will run `setup.bat` first automatically.

**Or manually:**
```bash
python main.py
```

The application launches in **paused mode** — the analysis worker will not run until you press **Resume**. This prevents errors if the backend isn't ready yet.

### First-time setup
1. Click **LLM Settings** and enter your Oobabooga endpoint URL, model name, and instruction template.
2. Click **Detect Context Size** to auto-detect, or set it manually.
3. Click **■ Select Region** and drag a rectangle over the game area you want to analyze.
4. Press **⏸ Pause** → it will change to **▶ Resume** — press **Resume** to start.

### Main controls

| Button | Function |
|--------|----------|
| **■ Select Region** | Click and drag to choose a screen region for analysis |
| **⏸ Pause / ▶ Resume** | Start or stop the analysis loop |
| **Character** | Edit character system prompt, screenshot analysis prompt, and select presets |
| **⏱ Timer** | Set a time window when analysis should run automatically |
| **LLM Settings** | Configure Oobabooga URL, model, instruction template, context/token limits |
| **Interval** | Set seconds between automatic screenshots (1-3600) |
| **TTS** | Enable/disable voice output, set language code, voice, speed, and test playback |
| **Web Advice** | Enable periodic web tip fetching with a search query or guide URL |
| **Alert** | Define a condition to watch for (the LLM checks it each cycle) |
| **History** | Browse, search, and view past analysis results |
| **Save** | Save all analysis results from the current session to a text file |
| **Hide Capture** | Toggle whether the app window hides during screenshot capture |

### Window management
- **Move** — drag the title bar
- **Resize** — drag any edge or corner of the window
- **Minimize** — click the `─` button
- **Maximize** — click the `□` button (double-click the title bar to toggle)
- **Close** — click the `✕` button to minimize to the system tray (use **Quit** in tray menu or context menu to exit fully)
- **Right-click** anywhere on the window for the full context menu
- **System tray** — right-click the blue dot icon for quick access

### Keyboard / Mouse shortcuts
- **Double-click title bar** — toggle maximize/restore
- **Right-click** — open context menu with all settings

---

## 🔧 Configuration

### Character / Prompt
Define who the AI companion is and what it should analyze in each screenshot. Choose from presets ("Bratty Coach") or write custom prompts. The **Clear Memory** button resets the conversation context.

### LLM / Oobabooga
Configure the endpoint URL (default: `http://localhost:5000/v1/chat/completions`), model name, instruction template (e.g., `ChatML`), context size, and max response tokens. The **Detect Context Size** button attempts to query the running Oobabooga instance.

### TTS (Kokoro)
- Language codes: `a` (American English), `b` (British English), `j` (Japanese), etc.
- Voice examples: `af_heart`, `af_bella`, `am_adam`, `bf_emma`
- Speed range: 0.5 – 2.0

### Web Advice
- Search query: plain text (e.g., `Elden Ring boss tips`) or a direct URL to a guide/wiki
- Interval: minimum 5 minutes between fetches
- Max snippets: 1–12

---

## 💡 Tips

- Start in **paused mode** — configure everything first, then press Resume
- Use **Timer** to only run analysis during your gaming hours
- The **status bar** shows live state: "Ready", "Paused", "Resumed", or "Backend offline — paused"
- If the backend becomes unreachable, the app **auto-pauses** to avoid error spam; just press Resume when the backend is back
- For the best experience, use a vision-optimized model (e.g., LLaVA, BakLLaVA, or CogVLM)

---

## 📄 License

This project is a fork of [PasiKoodaa/Screen-Analysis-Overlay](https://github.com/PasiKoodaa/Screen-Analysis-Overlay).

- TTS engine: [hexgrad/kokoro](https://github.com/hexgrad/kokoro), Kokoro-82M
- Local vision/chat backend: [Oobabooga/text-generation-webui](https://github.com/oobabooga/text-generation-webui)