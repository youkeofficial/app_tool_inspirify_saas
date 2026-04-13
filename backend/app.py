import os
import requests
import uuid
import textwrap
import logging
from flask import Flask, render_template, jsonify, send_from_directory, request
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from gtts import gTTS
from moviepy.editor import ImageClip, concatenate_videoclips, AudioFileClip
from threading import Thread

# --- CONFIGURATION & LOGGING ---
app = Flask(__name__)

log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s')
logger = logging.getLogger('quote_generator')
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(log_formatter)
    logger.addHandler(ch)
    
    fh = logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dev.log'))
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(log_formatter)
    logger.addHandler(fh)

logging.getLogger('werkzeug').setLevel(logging.WARNING)

@app.before_request
def log_request_info():
    if not request.path.startswith('/generated') and not request.path.startswith('/static'):
        logger.debug(f">>> REQ: {request.method} {request.url}")
        if request.is_json:
            logger.debug(f"    Payload: {request.get_json(silent=True)}")

@app.after_request
def log_response_info(response):
    if not request.path.startswith('/generated') and not request.path.startswith('/static'):
        logger.debug(f"<<< RES: {response.status} | {response.content_length} bytes")
    return response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GENERATED_DIR = os.path.join(BASE_DIR, 'generated')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
FONT_PATH = os.path.join(STATIC_DIR, 'font.ttf')

for d in [GENERATED_DIR, STATIC_DIR]:
    os.makedirs(d, exist_ok=True)

# --- WEBHOOK TOOL ---
def trigger_webhook(url, data):
    """Sends a POST request to the provided webhook URL in the background."""
    def send():
        try:
            logger.info(f"Triggering webhook: {url}")
            requests.post(url, json=data, timeout=10)
        except Exception as e:
            logger.error(f"Webhook failed: {e}")
    
    Thread(target=send).start()

# --- HELPERS ---
def api_response(status="success", data=None, message=None, code=200, webhook_url=None):
    """Standardized API response format + Webhook trigger."""
    response = {"status": status}
    if data: response.update(data)
    if message: response["message"] = message
    
    if webhook_url:
        trigger_webhook(webhook_url, response)
        
    return jsonify(response), code

def download_font():
    if not os.path.exists(FONT_PATH):
        try:
            logger.info("Downloading font...")
            url = "https://raw.githubusercontent.com/google/fonts/main/ofl/outfit/static/Outfit-Bold.ttf"
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            with open(FONT_PATH, 'wb') as f: f.write(r.content)
            logger.info("Font downloaded successfully.")
        except Exception as e:
            logger.error(f"Failed to download font: {e}")

def get_random_quote():
    try:
        r = requests.get("https://zenquotes.io/api/random", timeout=7)
        r.raise_for_status()
        data = r.json()
        return data[0]['q'], data[0]['a']
    except Exception as e:
        logger.warning(f"Quote API failed: {e}. Using fallback.")
        return "L'excellence n'est pas une action, c'est une habitude.", "Aristote"

def fetch_wikipedia_summary(subject, max_sentences=5):
    import wikipedia
    import re
    wikipedia.set_lang("fr")
    try:
        search_results = wikipedia.search(subject)
        if not search_results:
            return []
        page = wikipedia.page(search_results[0], auto_suggest=False)
        text = page.summary
        sentences = re.split(r'(?<=[.!?]) +', text)
        return [s for s in sentences if len(s.strip()) > 10][:max_sentences]
    except Exception as e:
        logger.error(f"Wiki fetch error: {e}")
        return []

def apply_random_animation(clip, duration):
    import random
    w, h = clip.size
    eff = random.choice(["zoom_in", "zoom_out"])
    
    try:
        if eff == "zoom_in":
            clip = clip.resized(lambda t: 1 + 0.05 * (t/max(duration, 0.1)))
            return clip.cropped(x_center=clip.w/2, y_center=clip.h/2, width=w, height=h)
        elif eff == "zoom_out":
            clip = clip.resized(lambda t: 1.1 - 0.05 * (t/max(duration, 0.1)))
            return clip.cropped(x_center=clip.w/2, y_center=clip.h/2, width=w, height=h)
    except Exception as e:
        logger.error(f"Animation error: {e}")
    return clip

# --- CORE LOGIC ---
def create_quote_image(text, author=""):
    try:
        for attempt in range(3):
            try:
                img_url = f"https://picsum.photos/1200/800?random={uuid.uuid4()}"
                res = requests.get(img_url, stream=True, timeout=15)
                res.raise_for_status()
                break
            except Exception as e:
                if attempt == 2: raise e
                import time; time.sleep(1)
        
        img = Image.open(res.raw).convert("RGB")
        img = ImageEnhance.Brightness(img).enhance(0.4)
        draw = ImageDraw.Draw(img)
        w, h = img.size
        
        download_font()
        font_size = int(h * 0.25)
        
        win_fonts = ["C:\\Windows\\Fonts\\arialbd.ttf", "C:\\Windows\\Fonts\\impact.ttf", "C:\\Windows\\Fonts\\georgiab.ttf"]
        
        try:
            font = ImageFont.truetype(FONT_PATH, font_size)
            a_font = ImageFont.truetype(FONT_PATH, int(font_size * 0.25))
        except:
            font = None
            for f_path in win_fonts:
                if os.path.exists(f_path):
                    try:
                        font = ImageFont.truetype(f_path, font_size)
                        a_font = ImageFont.truetype(f_path, int(font_size * 0.25))
                        break
                    except: continue
            if not font:
                try:
                    font = ImageFont.load_default(size=font_size)
                    a_font = ImageFont.load_default(size=int(font_size * 0.35))
                except:
                    font = ImageFont.load_default()
                    a_font = ImageFont.load_default()

        # Dynamic text scaling to prevent overflow
        while font_size > 20:
            try:
                test_font = ImageFont.truetype(FONT_PATH, font_size) if hasattr(font, 'font_variant') else font.font_variant(size=font_size)
            except:
                test_font = font
                
            avg_char_w = draw.textlength("A", font=test_font)
            if avg_char_w == 0: avg_char_w = font_size * 0.5
            
            wrap_width = max(10, int((w * 0.85) / avg_char_w))
            wrapper = textwrap.TextWrapper(width=wrap_width)
            lines = wrapper.wrap(text=text)
            
            line_heights = [(draw.textbbox((0, 0), l, font=test_font)[3] - draw.textbbox((0, 0), l, font=test_font)[1]) for l in lines]
            total_text_height = sum(line_heights) + (max(1, len(lines)) - 1) * 30
            
            if total_text_height <= h * 0.85:
                font = test_font
                break
                
            font_size -= 5
            
        current_y = (h - total_text_height) / 2
        
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            lw = bbox[2] - bbox[0]
            draw.text(((w-lw)/2, current_y), line, font=font, fill="white")
            current_y += line_heights[i] + 30
            
        if author:
            at = f"- {author}"
            aw = draw.textbbox((0,0), at, font=a_font)[2] - draw.textbbox((0,0), at, font=a_font)[0]
            draw.text(((w-aw)/2, current_y + 30), at, font=a_font, fill="#FFD700")

        fname = f"quote_{uuid.uuid4().hex[:8]}.jpg"
        img.save(os.path.join(GENERATED_DIR, fname), quality=90, optimize=True)
        return fname
    except Exception as e:
        logger.error(f"Image creation error: {e}")
        raise

# --- ROUTES ---
@app.route('/')
def home(): return render_template('index.html')

@app.route('/docs')
def docs(): return render_template('docs.html')

@app.route('/generated/<path:filename>')
def serve_files(filename): return send_from_directory(GENERATED_DIR, filename)

@app.route('/api/v1/library', methods=['GET'])
def api_library():
    files = os.listdir(GENERATED_DIR)
    return api_response(data={
        "images": sorted([f for f in files if f.startswith('quote_')], reverse=True),
        "audios": sorted([f for f in files if f.startswith('tts_')], reverse=True),
        "videos": sorted([f for f in files if f.startswith('video_')], reverse=True)
    })

@app.route('/api/v1/generate/image', methods=['POST'])
def api_gen_img():
    data = request.get_json() or {}
    text = data.get('text')
    author = data.get('author', "")
    webhook = data.get('webhook_url')
    
    if not text: text, author = get_random_quote()
    
    try:
        fname = create_quote_image(text, author)
        full_url = f"{request.url_root.rstrip('/')}/generated/{fname}"
        return api_response(data={"filename": fname, "url": full_url}, webhook_url=webhook)
    except Exception as e:
        return api_response(status="error", message="Failed to generate image", code=500, webhook_url=webhook)

@app.route('/api/v1/generate/tts', methods=['POST'])
def api_gen_tts():
    data = request.get_json() or {}
    text = data.get('text', '')
    webhook = data.get('webhook_url')
    
    if not text: return api_response(status="error", message="Text is required", code=400, webhook_url=webhook)
    
    try:
        fname = f"tts_{uuid.uuid4().hex[:8]}.mp3"
        tts = gTTS(text=text, lang='fr')
        tts.save(os.path.join(GENERATED_DIR, fname))
        full_url = f"{request.url_root.rstrip('/')}/generated/{fname}"
        return api_response(data={"filename": fname, "url": full_url}, webhook_url=webhook)
    except Exception as e:
        return api_response(status="error", message=str(e), code=500, webhook_url=webhook)

@app.route('/api/v1/generate/video', methods=['POST'])
def api_gen_vid():
    data = request.get_json() or {}
    imgs = data.get('images', [])
    aud = data.get('audio')
    webhook = data.get('webhook_url')
    
    if not imgs: return api_response(status="error", message="At least one image is required", code=400, webhook_url=webhook)
    
    try:
        valid_imgs = [i for i in imgs if os.path.exists(os.path.join(GENERATED_DIR, i))]
        if not valid_imgs: return api_response(status="error", message="Images not found", code=404, webhook_url=webhook)

        audio_clip = None
        if aud and os.path.exists(os.path.join(GENERATED_DIR, aud)):
            audio_clip = AudioFileClip(os.path.join(GENERATED_DIR, aud))
        
        duration = audio_clip.duration if audio_clip else 15.0
        sec_per_img = duration / len(valid_imgs)
        
        clips = []
        for i in valid_imgs:
            c = ImageClip(os.path.join(GENERATED_DIR, i)).set_duration(sec_per_img)
            c = apply_random_animation(c, sec_per_img)
            clips.append(c)
            
        video = concatenate_videoclips(clips, method="compose")
        if audio_clip: video = video.set_audio(audio_clip)
        
        fname = f"video_{uuid.uuid4().hex[:8]}.mp4"
        out_path = os.path.join(GENERATED_DIR, fname)
        video.write_videofile(out_path, fps=24, codec="libx264", audio_codec="aac", logger=None)
        
        video.close()
        if audio_clip: audio_clip.close()
        for c in clips: c.close()

        full_url = f"{request.url_root.rstrip('/')}/generated/{fname}"
        return api_response(data={"filename": fname, "url": full_url}, webhook_url=webhook)
    except Exception as e:
        logger.error(f"Video render failed: {e}")
        return api_response(status="error", message="Render failed", code=500, webhook_url=webhook)

@app.route('/api/v1/generate/wiki-story', methods=['POST'])
def api_gen_wiki_story():
    data = request.get_json() or {}
    subject = data.get('subject')
    webhook = data.get('webhook_url')
    max_sentences = data.get('max_sentences', 5)
    
    if not subject:
        return api_response(status="error", message="Subject is required", code=400, webhook_url=webhook)
        
    try:
        sentences = fetch_wikipedia_summary(subject, max_sentences=max_sentences)
        if not sentences:
            return api_response(status="error", message="Could not find information on Wikipedia.", code=404, webhook_url=webhook)
            
        full_text = " ".join(sentences)
        
        words = full_text.split()
        chunks = []
        for i in range(0, len(words), 12):
            chunk = " ".join(words[i:i+12])
            if chunk.strip():
                chunks.append(chunk)
                
        tts_fname = f"tts_{uuid.uuid4().hex[:8]}.mp3"
        tts_path = os.path.join(GENERATED_DIR, tts_fname)
        gTTS(text=full_text, lang='fr').save(tts_path)
        
        audio_clip = AudioFileClip(tts_path)
        duration = audio_clip.duration
        sec_per_img = duration / len(chunks)
        
        clips = []
        for s in chunks:
            img_fname = create_quote_image(text=s, author=subject)
            img_path = os.path.join(GENERATED_DIR, img_fname)
            c = ImageClip(img_path).set_duration(sec_per_img)
            c = apply_random_animation(c, sec_per_img)
            clips.append(c)
            
        video = concatenate_videoclips(clips, method="compose")
        video = video.set_audio(audio_clip)
        
        vid_fname = f"video_wiki_{uuid.uuid4().hex[:8]}.mp4"
        out_path = os.path.join(GENERATED_DIR, vid_fname)
        video.write_videofile(out_path, fps=24, codec="libx264", audio_codec="aac", logger=None)
        
        video.close()
        audio_clip.close()
        for c in clips: c.close()
        
        full_url = f"{request.url_root.rstrip('/')}/generated/{vid_fname}"
        return api_response(data={"filename": vid_fname, "url": full_url, "text": full_text}, webhook_url=webhook)
        
    except Exception as e:
        logger.error(f"Wiki story failed: {e}")
        return api_response(status="error", message=str(e), code=500, webhook_url=webhook)

# Legacy compatibility
@app.route('/generate', methods=['POST'])
def legacy_gen(): return api_gen_img()
@app.route('/history', methods=['GET'])
def legacy_hist(): return api_library()
@app.route('/tts', methods=['POST'])
def legacy_tts(): return api_gen_tts()
@app.route('/generate_video', methods=['POST'])
def legacy_vid(): return api_gen_vid()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
