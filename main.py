import os
import re
import asyncio
import uuid
from flask import Flask, render_template, request, send_from_directory, jsonify
import edge_tts
from pydub import AudioSegment

app = Flask(__name__)
os.makedirs("uploads", exist_ok=True)
os.makedirs("output", exist_ok=True)

VOICES = {
    "English US - Jenny (Female)": "en-US-JennyNeural",
    "English US - Guy (Male)": "en-US-GuyNeural",
    "English UK - Libby (Female)": "en-GB-LibbyNeural",
    "English UK - Ryan (Male)": "en-GB-RyanNeural",
    "French - Denise": "fr-FR-DeniseNeural",
    "Spanish - Elvira": "es-ES-ElviraNeural",
    "German - Katja": "de-DE-KatjaNeural",
    "Igbo - Ezinne": "ig-NG-EzinneNeural",
    "Yoruba - Ola": "yo-NG-OlaNeural",
    "Hausa - Salma": "ha-NG-SalmaNeural",
}

def parse_srt(path):
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    pattern = re.compile(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\Z)', re.DOTALL)
    subs = []
    for m in pattern.finditer(content):
        subs.append({
            "start": srt_to_ms(m.group(2)),
            "end": srt_to_ms(m.group(3)),
            "text": m.group(4).strip().replace('\n', ' ')
        })
    return subs

def srt_to_ms(t):
    h, m, s_ms = t.split(':')
    s, ms = s_ms.split(',')
    return int(h)*3600000 + int(m)*60000 + int(s)*1000 + int(ms)

async def generate_audio(subs, voice, output_path):
    final_audio = AudioSegment.empty()
    last_end = 0
    for sub in subs:
        silence_duration = sub["start"] - last_end
        if silence_duration > 0:
            final_audio += AudioSegment.silent(duration=silence_duration)

        temp_file = f"output/_temp_{uuid.uuid4().hex}.mp3"
        communicate = edge_tts.Communicate(sub["text"], voice)
        await communicate.save(temp_file)

        spoken = AudioSegment.from_file(temp_file)
        os.remove(temp_file)
        slot_duration = sub["end"] - sub["start"]
        if len(spoken) > slot_duration:
            spoken = spoken[:slot_duration]
        final_audio += spoken
        last_end = sub["end"]
    final_audio.export(output_path, format="mp3")
    return output_path

@app.route('/')
def index():
    return render_template('index.html', voices=VOICES)

@app.route('/convert', methods=['POST'])
def convert(): # <-- NO async for Render/gunicorn
    file = request.files.get('srt_file')
    voice = request.form.get('voice')
    if not file or not voice:
        return jsonify({"error": "Missing file or voice"}), 400

    srt_path = os.path.join("uploads", f"{uuid.uuid4().hex}.srt")
    file.save(srt_path)
    subs = parse_srt(srt_path)
    if not subs:
        return jsonify({"error": "Could not parse SRT"}), 400

    output_filename = f"{uuid.uuid4().hex}.mp3"
    output_path = os.path.join("output", output_filename)

    asyncio.run(generate_audio(subs, voice, output_path))
    os.remove(srt_path)

    return jsonify({"audio_url": f"/output/{output_filename}", "segments": len(subs)})

@app.route('/output/<path:filename>')
def serve_output(filename):
    return send_from_directory('output', filename)

if __name__ == '__main__':
    app.run()