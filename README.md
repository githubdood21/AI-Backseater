# AI-Backseater

This application provides a transparent overlay for automated image analysis using an Oobabooga/OpenAI-compatible vision endpoint. It captures screenshots of a selected region or the entire screen in memory and analyzes them using AI, providing descriptions and alerts based on user-defined conditions. Currently tested only on Windows, but might be also Linux-compatible.


## Features

- Transparent overlay that stays on top of other windows
- Customizable capture region selection
- Automated screen analysis using Oobabooga
- Customizable system prompts for analysis
- Character prompt plus rolling conversation memory
- Built-in "Bratty Coach" character preset
- Pause/Resume functionality
- Alert system for specific conditions
- Ability to save analysis results
- Resizable overlay
- Hide/show buttons by double clicking the overlay
- Toggle overlay visibility during screenshots
- Saves analysis history to SQL database
- Search and view analysis history
- Export analysis history to JSON or CSV file
- Set analysis Start and End times
- Configure Oobabooga endpoint and model
- Configure the Oobabooga instruction template
- Configure context size and response token budget
- Set automatic screenshot interval
- Voice output through the local Kokoro TTS repo
- Optional periodic web advice snippets for game tips

## Requirements

- Python 3.10+
- PyQt5
- Pillow
- requests
- Kokoro TTS

For Kokoro on Windows, install `espeak-ng` separately if the selected voice/language requires it.
 
## Installation

1. Clone this repository:
   ```
   git clone https://github.com/githubdood21/AI-Backseater.git
   cd AI-Backseater
   ```


2. Set up a Python environment:

   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Ensure Oobabooga/text-generation-webui is running with an OpenAI-compatible vision endpoint. The default URL is `http://localhost:5000/v1/chat/completions`.
4. Optional: clone Kokoro into a local `kokoro/` folder if you want to use a development checkout. Otherwise the published `kokoro` package from `requirements.txt` is used.

## Usage

1. Run the application:
   ```
   python main.py
   ```

2. Use the buttons or right-click context menu to:
   - View history and search history
   - Export history to JSON or CSV
   - Select a capture region
   - Update the analysis prompt
   - Pause/Resume analysis
   - Set alert conditions
   - Save analysis results
   - Resize the overlay
   - Toggle overlay visibility during screenshots
   - Configure Oobabooga endpoint/model
   - Set the automatic analysis interval
   - Configure Kokoro TTS voice output
   - Configure periodic web advice search

4. The overlay will continuously capture and analyze the selected region, displaying results in real-time.

## Configuration
![kobo](https://github.com/user-attachments/assets/c8781ff4-b7c5-47a4-b72e-84da4a5e3ea2)

- Adjust the `OOBA_OPENAI_URL` variable in the script or use "Oobabooga Settings" if your Oobabooga server is running on a different address.
- Use "Character/Prompt" to change who the companion is and what it should do with each screenshot.
- Use "Oobabooga Settings" to set or auto-detect the context size. Older memory messages are dropped first when the context budget is full.
- Use "TTS Settings" to enable or disable Kokoro voice output, set language/voice, adjust speed, and test playback.
- Use "Web Advice" to enable periodic tip fetching. You can provide a search query or a direct guide/wiki URL. The newest snippets are injected into the LLM context when relevant.

## Using Oobabooga

1. Ensure Oobabooga/text-generation-webui is running with OpenAI-compatible API support.
2. Load a vision-capable model.
3. In the application, click "Oobabooga Settings".
4. Enter the desired endpoint, model name, instruction template, context size, and response token budget.
5. Click "OK" to confirm the selection.

## Credits

- Original project: [PasiKoodaa/Screen-Analysis-Overlay](https://github.com/PasiKoodaa/Screen-Analysis-Overlay)
- TTS engine: [hexgrad/kokoro](https://github.com/hexgrad/kokoro), Kokoro-82M
- Local vision/chat backend support is designed around Oobabooga/text-generation-webui's OpenAI-compatible API.

