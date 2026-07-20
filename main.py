"""
VocabVideo API - FastAPI Backend
Deploy: Render.com (free tier)
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import os, uuid, shutil, tempfile
import urllib.request, zipfile, io, json
from typing import List
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS

app = FastAPI(title="VocabVideo API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class VocabItem(BaseModel):
    english: str
    vietnamese: str

class GenerateRequest(BaseModel):
    vocab: List[VocabItem]
    highlight_color: str = "#ffd54f"
    bg_color: str = "#1ebc46"
    en_text_color: str = "#ffffff"
    vi_text_color: str = "#1565c0"
    pill_bg_color: str = "#ffffff"
    font_family: str = "Arial"
    google_font: str = ""
    cols: int = 3
    row_spacing: int = 60
    voice_accent: str = "com"

import re

def hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

import json

def get_google_font_path(family, tmp_dir="/tmp/vocab_fonts"):
    """Download Google Font with Vietnamese subset. Returns None if font doesn't support Vietnamese."""
    os.makedirs(tmp_dir, exist_ok=True)
    safe_name = family.replace(" ", "_")
    font_path = os.path.join(tmp_dir, safe_name + "_vi2.ttf")
    
    if os.path.exists(font_path):
        return font_path
        
    try:
        api_name = family.lower().replace(' ', '-')
        url = f"https://gwfh.mranftl.com/api/fonts/{api_name}?subsets=vietnamese,latin,latin-ext"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            # Check if this font actually supports vietnamese
            subset_map = data.get("subsetMap", {})
            if not subset_map.get("vietnamese", False):
                print(f"Font {family} does not support Vietnamese")
                return None
            
            variants = data.get("variants", [])
            if not variants: return None
            
            target_variant = None
            for v in variants:
                if v.get("id") == "700":
                    target_variant = v
                    break
            if not target_variant:
                for v in variants:
                    if v.get("id") in ["regular", "400"]:
                        target_variant = v
                        break
            if not target_variant:
                target_variant = variants[0]
                
            ttf_url = target_variant.get("ttf")
            if ttf_url:
                req2 = urllib.request.Request(ttf_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req2, timeout=15) as f_res, open(font_path, 'wb') as f_out:
                    f_out.write(f_res.read())
                return font_path
    except Exception as e:
        print("Error downloading font via GWFH:", e)
        
    return None

VI_FALLBACK_FONT = "/tmp/vocab_fonts/_vi_fallback.ttf"

def ensure_vi_fallback():
    """Ensure a Vietnamese fallback font (Noto Sans) is downloaded."""
    if os.path.exists(VI_FALLBACK_FONT):
        return VI_FALLBACK_FONT
    try:
        os.makedirs("/tmp/vocab_fonts", exist_ok=True)
        url = "https://gwfh.mranftl.com/api/fonts/noto-sans?subsets=vietnamese,latin"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            variants = data.get('variants', [])
            for v in variants:
                if v.get('id') == '700':
                    ttf_url = v.get('ttf')
                    req2 = urllib.request.Request(ttf_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req2, timeout=15) as f, open(VI_FALLBACK_FONT, 'wb') as out:
                        out.write(f.read())
                    return VI_FALLBACK_FONT
    except Exception as e:
        print("Error downloading VI fallback font:", e)
    return None

def get_font(size, bold=False, family="Arial", google_font=""):
    """Get font for English text. Uses Google Font if specified."""
    paths = (
        ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
        if bold else
        ["/System/Library/Fonts/Supplemental/Arial.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]
    )
    if google_font:
        # For English text, try to get any variant (don't require VI subset)
        gpath = _get_any_google_font(google_font)
        if gpath:
            paths = [gpath] + paths
    elif family == "Tahoma":
        paths = ["/System/Library/Fonts/Supplemental/Tahoma Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Tahoma.ttf"] + paths
    elif family == "Verdana":
        paths = ["/System/Library/Fonts/Supplemental/Verdana Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Verdana.ttf"] + paths
    elif family == "Comic Sans MS":
        paths = ["/System/Library/Fonts/Supplemental/Comic Sans MS Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Comic Sans MS.ttf"] + paths
    elif family == "Times New Roman":
        paths = ["/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Times New Roman.ttf"] + paths
    elif family == "Courier New":
        paths = ["/System/Library/Fonts/Supplemental/Courier New Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Courier New.ttf"] + paths
        
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)

def _get_any_google_font(family, tmp_dir="/tmp/vocab_fonts"):
    """Download any variant of a Google Font (for English text, no VI required)."""
    os.makedirs(tmp_dir, exist_ok=True)
    safe_name = family.replace(" ", "_")
    font_path = os.path.join(tmp_dir, safe_name + "_en.ttf")
    if os.path.exists(font_path):
        return font_path
    try:
        api_name = family.lower().replace(' ', '-')
        url = f"https://gwfh.mranftl.com/api/fonts/{api_name}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            variants = data.get("variants", [])
            if not variants: return None
            target = None
            for v in variants:
                if v.get("id") == "700": target = v; break
            if not target:
                for v in variants:
                    if v.get("id") in ["regular","400"]: target = v; break
            if not target: target = variants[0]
            ttf_url = target.get("ttf")
            if ttf_url:
                req2 = urllib.request.Request(ttf_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req2, timeout=15) as f_res, open(font_path, 'wb') as f_out:
                    f_out.write(f_res.read())
                return font_path
    except Exception as e:
        print("Error getting English font:", e)
    return None

def get_vi_font(size):
    """Get font for Vietnamese text - always Vietnamese-capable."""
    # First ensure fallback exists
    vi_path = ensure_vi_fallback()
    paths = []
    if vi_path and os.path.exists(vi_path):
        paths.append(vi_path)
    # System Vietnamese-capable fallbacks
    paths += [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)

def draw_rounded_rect(draw, xy, r, fill):
    x1,y1,x2,y2 = xy
    r = min(r, (x2 - x1) // 2, (y2 - y1) // 2)
    if r < 0: return
    draw.rectangle([x1+r,y1,x2-r,y2], fill=fill)
    draw.rectangle([x1,y1+r,x2,y2-r], fill=fill)
    for ex,ey in [(x1,y1),(x2-2*r,y1),(x1,y2-2*r),(x2-2*r,y2-2*r)]:
        draw.ellipse([ex,ey,ex+2*r,ey+2*r], fill=fill)

def wrap_text(text, font, max_width, draw):
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        test_line = " ".join(current_line + [word])
        if draw.textbbox((0,0), test_line, font=font)[2] <= max_width:
            current_line.append(word)
        else:
            if not current_line:
                lines.append(word)
            else:
                lines.append(" ".join(current_line))
                current_line = [word]
    if current_line:
        lines.append(" ".join(current_line))
    return lines

def get_fonts_and_metrics(vocab, cw, cfg, draw):
    ef = get_font(42, bold=True, family=cfg["font_family"], google_font=cfg.get("google_font", ""))
    max_ew = max([draw.textbbox((0,0), w[0], font=ef)[2] - draw.textbbox((0,0), w[0], font=ef)[0] for w in vocab]) if vocab else 0
    if max_ew > cw - 14:
        new_size = max(14, int(42 * (cw - 14) / max_ew))
        ef = get_font(new_size, bold=True, family=cfg["font_family"], google_font=cfg.get("google_font", ""))

    vi_gf = cfg.get("google_font", "")
    vi_gf_path = get_google_font_path(vi_gf) if vi_gf else None
    if vi_gf_path:
        vf = ImageFont.truetype(vi_gf_path, 28)
    else:
        vf = get_vi_font(28)
    
    bbox_en = draw.textbbox((0,0), "Ag", font=ef, anchor="ma")
    en_top = bbox_en[1]
    std_eh = bbox_en[3] - bbox_en[1]
    
    bbox_vi = draw.textbbox((0,0), "Ag", font=vf, anchor="ma")
    vi_top = bbox_vi[1]
    std_vh = bbox_vi[3] - bbox_vi[1]
    
    return ef, vf, en_top, std_eh, vi_top, std_vh

def draw_word_block(draw, en, vi, cx, y1, cell_h, active, cfg, ef, vf, en_top, std_eh, vi_top, std_vh, cw):
    pill_pad_x = 26
    pill_pad_y = 10
    en_to_pill_gap = 27
    
    max_vi_width = max(80, cw - 2*pill_pad_x - 10)
    vi_lines = wrap_text(vi, vf, max_vi_width, draw)
    n_vi_lines = len(vi_lines)
    
    vh = n_vi_lines * std_vh + 7 * (n_vi_lines - 1)
    pill_h = vh + 2 * pill_pad_y
    block_h = std_eh + en_to_pill_gap + pill_h
    block_top = y1 + max(0, (cell_h - block_h) // 2)
    
    ey = block_top
    vy = ey + std_eh + en_to_pill_gap
    
    fill_color = cfg["hl_card"] if active else cfg.get("en_text", (255, 255, 255))
    draw.text((cx, ey), en, font=ef, fill=fill_color, anchor="mt")
    
    pill_bg = cfg.get("pill_bg", (255,255,255))
    vi_color = cfg.get("vi_text", (21, 101, 192))
    vw = max([draw.textbbox((0,0), l, font=vf)[2] - draw.textbbox((0,0), l, font=vf)[0] for l in vi_lines]) if vi_lines else 0
    draw_rounded_rect(draw, (cx-vw//2-pill_pad_x, vy-pill_pad_y, cx+vw//2+pill_pad_x, vy+vh+pill_pad_y), 20, pill_bg)
    
    curr_y = vy
    for l in vi_lines:
        draw.text((cx, curr_y), l, font=vf, fill=vi_color, anchor="mt")
        curr_y += std_vh + 7

def render_frame(vocab, positions, active_idx, cfg, skip_idx=None):
    W,H = 720,1280
    img = Image.new("RGB", (W,H), cfg["bg"])
    draw = ImageDraw.Draw(img, "RGBA")
    cw = positions[0][2] - positions[0][0] if positions else 204
    ef, vf, en_top, std_eh, vi_top, std_vh = get_fonts_and_metrics(vocab, cw, cfg, draw)

    for i,((en,vi),(x1,y1,x2,y2)) in enumerate(zip(vocab, positions)):
        if skip_idx is not None and i == skip_idx:
            continue
            
        cx = x1 + cw//2
        cell_h = y2 - y1
        active = (i == active_idx)
        
        draw_word_block(draw, en, vi, cx, y1, cell_h, active, cfg, ef, vf, en_top, std_eh, vi_top, std_vh, cw)

    return img

def render_word_cell(item, pos, cfg, ef, vf, en_top, std_eh, vi_top, std_vh, cw):
    en, vi = item
    x1, y1, x2, y2 = pos
    cell_h = y2 - y1
    
    img = Image.new("RGBA", (cw, cell_h), (0,0,0,0))
    draw = ImageDraw.Draw(img, "RGBA")
    
    # cx is local to the new image
    cx = cw // 2
    y_local = 0
    
    draw_word_block(draw, en, vi, cx, y_local, cell_h, True, cfg, ef, vf, en_top, std_eh, vi_top, std_vh, cw)
    return img

def calc_positions(n, cols, cfg, vocab=None):
    W=720; mx=40; gx=14; gy=cfg.get("row_spacing", 40); top=67
    cw=(W-2*mx-(cols-1)*gx)//cols

    # Base heights
    en_h = 44
    pill_pad_y = 10
    vi_line_h = 28
    vi_line_gap = 7
    en_to_pill_gap = 27
    word_top_pad = 7

    def cell_height_for_vi_lines(n_lines):
        pill_h = n_lines * vi_line_h + vi_line_gap * (n_lines - 1) + 2 * pill_pad_y
        return word_top_pad + en_h + en_to_pill_gap + pill_h + word_top_pad

    # Calculate how many VI lines each word needs
    if vocab:
        dummy_img = Image.new("RGB", (100, 100))
        dummy_draw = ImageDraw.Draw(dummy_img)
        vi_gf = cfg.get("google_font", "")
        vi_gf_path = get_google_font_path(vi_gf) if vi_gf else None
        if vi_gf_path:
            vf = ImageFont.truetype(vi_gf_path, vi_line_h)
        else:
            vf = get_vi_font(vi_line_h)
        pill_pad_x = 40
        max_vi_width = max(100, cw - 2 * pill_pad_x - 10)
        vi_line_counts = [len(wrap_text(v, vf, max_vi_width, dummy_draw)) for _, v in vocab]
    else:
        vi_line_counts = [1] * n

    # Compute per-row max height
    num_rows = (n + cols - 1) // cols
    row_heights = []
    for r in range(num_rows):
        row_items = vi_line_counts[r * cols: r * cols + cols]
        max_lines = max(row_items) if row_items else 1
        row_heights.append(cell_height_for_vi_lines(max_lines))

    # Build positions
    pos = []
    y_cursor = top
    for r in range(num_rows):
        ch = row_heights[r]
        for c in range(cols):
            i = r * cols + c
            if i >= n:
                break
            x1 = mx + c * (cw + gx)
            pos.append((x1, y_cursor, x1 + cw, y_cursor + ch))
        y_cursor += row_heights[r] + gy

    return pos


def update_status(job_id, data):
    try:
        with open(f"/tmp/status_{job_id}.json", "w") as f:
            json.dump(data, f)
    except:
        pass

@app.post("/generate")
def start_generate(req: GenerateRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())[:8]
    update_status(job_id, {"status": "processing", "progress": 0, "total": len(req.vocab), "detail": "Đang chuẩn bị..."})
    background_tasks.add_task(generate_video_task, req, job_id)
    return {"job_id": job_id}

@app.get("/status/{job_id}")
def get_status(job_id: str):
    path = f"/tmp/status_{job_id}.json"
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {"status": "unknown"}

@app.get("/download/{job_id}")
def download_video(job_id: str):
    path = f"/tmp/vocabvideo_{job_id}.mp4"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(path, media_type="video/mp4", filename="Vocabulary_Video.mp4")

def generate_video_task(req: GenerateRequest, job_id: str):
    tmp = tempfile.mkdtemp(prefix=f"vocab_{job_id}_")

    try:
        vocab = [(v.english, v.vietnamese) for v in req.vocab]
        cfg   = {
            "bg":             hex_to_rgb(req.bg_color),
            "hl_card":        hex_to_rgb(req.highlight_color),
            "en_text":        hex_to_rgb(req.en_text_color),
            "vi_text":        hex_to_rgb(req.vi_text_color),
            "pill_bg":        hex_to_rgb(req.pill_bg_color),
            "font_family":    req.font_family,
            "google_font":    req.google_font,
            "row_spacing":    req.row_spacing,
        }
        cols     = req.cols
        positions = calc_positions(len(vocab), cols, cfg, vocab=vocab)

        # We need the fonts to calculate cell_w, cell_h, cw etc.
        cw = positions[0][2] - positions[0][0] if positions else 204
        W,H = 720,1280
        tmp_img = Image.new("RGB", (W,H))
        tmp_draw = ImageDraw.Draw(tmp_img)
        ef, vf, en_top, std_eh, vi_top, std_vh = get_fonts_and_metrics(vocab, cw, cfg, tmp_draw)

        # Generate TTS
        audio_paths = []
        for i,(en,vi) in enumerate(vocab):
            update_status(job_id, {"status": "processing", "progress": 0, "total": len(vocab), "detail": f"Đang tạo giọng đọc ({i+1}/{len(vocab)})..."})
            ep = os.path.join(tmp, f"en_{i}.mp3")
            gTTS(en.replace("/"," "), lang="en", tld=req.voice_accent).save(ep)
            audio_paths.append(ep)

        import subprocess, gc
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

        def make_video_from_image_and_audio(img_path, audio_path, out_path, duration=None):
            """Use FFmpeg directly to combine a static image + audio into a video clip."""
            if audio_path:
                cmd = [
                    ffmpeg_exe, "-y",
                    "-loop", "1", "-i", img_path,
                    "-i", audio_path,
                    "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
                    "-c:a", "aac", "-b:a", "64k",
                    "-pix_fmt", "yuv420p",
                    "-shortest",
                    out_path
                ]
            else:
                cmd = [
                    ffmpeg_exe, "-y",
                    "-loop", "1", "-i", img_path,
                    "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
                    "-pix_fmt", "yuv420p",
                    "-t", str(duration or 1.0),
                    "-an",
                    out_path
                ]
            subprocess.run(cmd, check=True, capture_output=True)

        def make_silence_wav(out_path, duration):
            """Generate silence WAV with FFmpeg."""
            cmd = [
                ffmpeg_exe, "-y",
                "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
                "-t", str(duration),
                "-c:a", "pcm_s16le",
                out_path
            ]
            subprocess.run(cmd, check=True, capture_output=True)

        def concat_audio_clips(parts, out_path):
            """Concatenate audio files using FFmpeg."""
            list_path = out_path + "_alist.txt"
            with open(list_path, "w") as f:
                for p in parts:
                    f.write(f"file '{p}'\n")
            cmd = [ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", out_path]
            subprocess.run(cmd, check=True, capture_output=True)
            os.remove(list_path)

        def overlay_zoom_word(bg_path, word_png_path, pos, audio_path, out_path, fps=15):
            """
            Overlay a zoomed animated word on background using FFmpeg overlay filter.
            pos = (x1, y1, x2, y2)
            """
            x1, y1, x2, y2 = pos
            cell_w = x2 - x1
            cell_h = y2 - y1
            # We'll use FFmpeg's overlay filter with scale animation
            # Zoom: scale from 115% back to 100% over first 0.3s
            # For simplicity (Render free tier), just do a single-frame blend  
            # FFmpeg zoompan is CPU-heavy; use a simple 2-frame approach instead
            
            # Get audio duration
            probe_cmd = [ffmpeg_exe, "-i", audio_path, "-f", "null", "-"]
            result = subprocess.run(probe_cmd, capture_output=True, text=True)
            duration = None
            for line in result.stderr.split('\n'):
                if 'Duration' in line:
                    try:
                        t = line.split('Duration:')[1].split(',')[0].strip()
                        h, m, s = t.split(':')
                        duration = int(h)*3600 + int(m)*60 + float(s)
                        break
                    except:
                        pass
            if not duration:
                duration = 2.0
            total_dur = 0.3 + duration + 0.8  # silence_before + audio + silence_after

            # Build full silence audio
            silence_before = out_path + "_sb.wav"
            silence_after = out_path + "_sa.wav"
            make_silence_wav(silence_before, 0.3)
            make_silence_wav(silence_after, 0.8)
            
            # Convert MP3 to standard WAV (44100Hz, stereo, pcm_s16le) for safe concatenation
            audio_wav = out_path + "_audio.wav"
            cmd_conv = [
                ffmpeg_exe, "-y", "-i", audio_path,
                "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le",
                audio_wav
            ]
            subprocess.run(cmd_conv, check=True, capture_output=True)
            
            full_audio = out_path + "_full_audio.aac"
            concat_audio_clips([silence_before, audio_wav, silence_after], out_path + "_full.wav")

            # Convert to AAC
            cmd_aac = [ffmpeg_exe, "-y", "-i", out_path + "_full.wav", "-c:a", "aac", "-b:a", "64k", full_audio]
            subprocess.run(cmd_aac, check=True, capture_output=True)

            # Overlay word PNG (RGBA with alpha) on background using FFmpeg
            overlay_x = x1
            overlay_y = y1
            # Use alpha_mode=straight to properly handle PNG transparency
            filter_str = (
                f"[0:v][1:v]overlay={overlay_x}:{overlay_y}:alpha=straight,format=yuv420p[v]"
            )
            cmd = [
                ffmpeg_exe, "-y",
                "-loop", "1", "-t", str(total_dur), "-i", bg_path,
                "-loop", "1", "-t", str(total_dur), "-i", word_png_path,
                "-i", full_audio,
                "-filter_complex", filter_str,
                "-map", "[v]", "-map", "2:a",
                "-c:v", "libx264", "-preset", "ultrafast",
                "-c:a", "aac", "-b:a", "64k",
                "-t", str(total_dur),
                out_path
            ]
            subprocess.run(cmd, check=True, capture_output=True)

            # Cleanup temp audio files
            for f in [silence_before, silence_after, audio_wav, full_audio, out_path + "_full.wav"]:
                try: os.remove(f)
                except: pass

        temp_videos = []

        # --- Intro (static frame, silent audio, 1.0s) ---
        update_status(job_id, {"status": "processing", "progress": 0, "total": len(vocab), "detail": "Đang tạo intro..."})
        intro_img = render_frame(vocab, positions, -1, cfg)
        intro_path = os.path.join(tmp, "intro.png")
        intro_img.save(intro_path)
        del intro_img
        gc.collect()

        intro_mp4 = os.path.join(tmp, "intro.mp4")
        intro_silence = os.path.join(tmp, "intro_silence.wav")
        make_silence_wav(intro_silence, 1.0)
        make_video_from_image_and_audio(intro_path, intro_silence, intro_mp4)
        temp_videos.append(intro_mp4)

        # --- Per-word clips ---
        for i, (en, vi) in enumerate(vocab):
            update_status(job_id, {"status": "processing", "progress": i, "total": len(vocab), "detail": f"Đang render từ {i+1}/{len(vocab)}..."})
            ep = audio_paths[i]

            # Render bg frame (all words shown, active word NOT highlighted by background)
            bg_img = render_frame(vocab, positions, active_idx=i, cfg=cfg, skip_idx=i)
            bg_path = os.path.join(tmp, f"bg_{i}.png")
            bg_img.save(bg_path)
            del bg_img
            gc.collect()

            # Render the highlighted active word cell as RGBA PNG
            pos = positions[i]
            word_img = render_word_cell((en, vi), pos, cfg, ef, vf, en_top, std_eh, vi_top, std_vh, cw)
            word_path = os.path.join(tmp, f"word_{i}.png")
            word_img.save(word_path)
            del word_img
            gc.collect()

            # Combine using FFmpeg overlay
            word_mp4 = os.path.join(tmp, f"word_{i}.mp4")
            overlay_zoom_word(bg_path, word_path, pos, ep, word_mp4)
            temp_videos.append(word_mp4)
            gc.collect()

        # --- Outro (static frame, silent audio, 1.5s) ---
        update_status(job_id, {"status": "processing", "progress": len(vocab), "total": len(vocab), "detail": "Đang tạo outro..."})
        outro_img = render_frame(vocab, positions, -1, cfg)
        outro_path = os.path.join(tmp, "outro.png")
        outro_img.save(outro_path)
        del outro_img
        gc.collect()

        outro_mp4 = os.path.join(tmp, "outro.mp4")
        outro_silence = os.path.join(tmp, "outro_silence.wav")
        make_silence_wav(outro_silence, 1.5)
        make_video_from_image_and_audio(outro_path, outro_silence, outro_mp4)
        temp_videos.append(outro_mp4)

        # Final concatenation
        update_status(job_id, {"status": "processing", "progress": len(vocab), "total": len(vocab), "detail": "Đang ghép nối video..."})
        list_file = os.path.join(tmp, "list.txt")
        with open(list_file, "w") as f:
            for p in temp_videos:
                f.write(f"file '{p}'\n")

        out_path = os.path.join(tmp, "output.mp4")
        cmd = [
            ffmpeg_exe, "-y", "-f", "concat", "-safe", "0",
            "-i", list_file, "-c", "copy", out_path
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        result_path = f"/tmp/vocabvideo_{job_id}.mp4"
        shutil.copy(out_path, result_path)
        shutil.rmtree(tmp)

        update_status(job_id, {"status": "done", "detail": "Hoàn tất!"})

    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        import traceback
        traceback.print_exc()
        update_status(job_id, {"status": "error", "detail": str(e)})

@app.get("/api/test_voice")
def test_voice(tld: str = "com", background_tasks: BackgroundTasks = None):
    try:
        fd, path = tempfile.mkstemp(suffix=".mp3", prefix="test_voice_")
        os.close(fd)
        gTTS("Hello, this is a voice test.", lang="en", tld=tld).save(path)
        if background_tasks:
            background_tasks.add_task(os.remove, path)
        return FileResponse(path, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok"}
