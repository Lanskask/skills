# /// script
# requires-python = ">=3.10"
# dependencies = ["faster-whisper>=1.2", "tokenizers>=0.21", "onnxruntime>=1.18", "av>=16,<17"]
# ///
"""Last-resort transcription. usage: whisper_worker.py AUDIO OUT.json MODEL [LANG] [START END]  (seconds; timestamps stay absolute)
Greedy decoding (beam 1, temperature 0, VAD on) so the same audio gives the same text on the same machine."""
import json
import sys

from faster_whisper import WhisperModel

audio, out, model = sys.argv[1], sys.argv[2], sys.argv[3]
lang = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] != "auto" else None
m = WhisperModel(model, device="auto", compute_type="int8")
clip = [float(sys.argv[5]), float(sys.argv[6])] if len(sys.argv) > 6 else None
kw = {"clip_timestamps": clip} if clip else {}
segs, info = m.transcribe(audio, language=lang, beam_size=1, temperature=0.0, vad_filter=not clip, **kw)
cues = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for s in segs if s.text.strip()]
json.dump({"language": info.language, "cues": cues}, open(out, "w", encoding="utf-8"), ensure_ascii=False)
print(f"{len(cues)} cues, language={info.language}")
