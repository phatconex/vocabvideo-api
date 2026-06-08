"""
VocabVideo API - FastAPI Backend
Deploy: Render.com (free tier)
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import os, uuid, shutil, tempfile, numpy as np
import urllib.request, zipfile, io
from typing import List
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS
from moviepy import *

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
    ef = get_font(64, bold=True, family=cfg["font_family"], google_font=cfg.get("google_font", ""))
    max_ew = max([draw.textbbox((0,0), w[0], font=ef)[2] - draw.textbbox((0,0), w[0], font=ef)[0] for w in vocab]) if vocab else 0
    if max_ew > cw - 20:
        new_size = max(20, int(64 * (cw - 20) / max_ew))
        ef = get_font(new_size, bold=True, family=cfg["font_family"], google_font=cfg.get("google_font", ""))

    vi_gf = cfg.get("google_font", "")
    vi_gf_path = get_google_font_path(vi_gf) if vi_gf else None
    if vi_gf_path:
        vf = ImageFont.truetype(vi_gf_path, 42)
    else:
        vf = get_vi_font(42)
    
    bbox_en = draw.textbbox((0,0), "Ag", font=ef, anchor="ma")
    en_top = bbox_en[1]
    std_eh = bbox_en[3] - bbox_en[1]
    
    bbox_vi = draw.textbbox((0,0), "Ag", font=vf, anchor="ma")
    vi_top = bbox_vi[1]
    std_vh = bbox_vi[3] - bbox_vi[1]
    
    return ef, vf, en_top, std_eh, vi_top, std_vh

def draw_word_block(draw, en, vi, cx, y1, cell_h, active, cfg, ef, vf, en_top, std_eh, vi_top, std_vh, cw):
    pill_pad_x = 40
    pill_pad_y = 15
    en_to_pill_gap = 40
    
    max_vi_width = max(100, cw - 2*pill_pad_x - 10)
    vi_lines = wrap_text(vi, vf, max_vi_width, draw)
    n_vi_lines = len(vi_lines)
    
    vh = n_vi_lines * std_vh + 10 * (n_vi_lines - 1)
    pill_h = vh + 2 * pill_pad_y
    block_h = std_eh + en_to_pill_gap + pill_h
    block_top = y1 + (cell_h - block_h) // 2
    
    ey = block_top
    vy = ey + std_eh + en_to_pill_gap
    
    fill_color = cfg["hl_card"] if active else cfg.get("en_text", (255, 255, 255))
    draw.text((cx, ey - en_top), en, font=ef, fill=fill_color, anchor="ma")
    
    pill_bg = cfg.get("pill_bg", (255,255,255))
    vi_color = cfg.get("vi_text", (21, 101, 192))
    vw = max([draw.textbbox((0,0), l, font=vf)[2] - draw.textbbox((0,0), l, font=vf)[0] for l in vi_lines]) if vi_lines else 0
    draw_rounded_rect(draw, (cx-vw//2-pill_pad_x, vy-pill_pad_y, cx+vw//2+pill_pad_x, vy+vh+pill_pad_y), 30, pill_bg)
    
    curr_y = vy
    for l in vi_lines:
        draw.text((cx, curr_y - vi_top), l, font=vf, fill=vi_color, anchor="ma")
        curr_y += std_vh + 10

def render_frame(vocab, positions, active_idx, cfg, skip_idx=None):
    W,H = 1080,1920
    img = Image.new("RGB", (W,H), cfg["bg"])
    draw = ImageDraw.Draw(img, "RGBA")
    cw = positions[0][2] - positions[0][0] if positions else 306
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
    W=1080; mx=60; gx=20; gy=cfg.get("row_spacing", 60); top=100
    cw=(W-2*mx-(cols-1)*gx)//cols

    # Base heights
    en_h = 64   # approx English text height
    pill_pad_y = 15
    vi_line_h = 42  # approx Vietnamese line height
    vi_line_gap = 10
    en_to_pill_gap = 40
    word_top_pad = 10

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


@app.post("/generate")
def generate_video(req: GenerateRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())[:8]
    tmp    = tempfile.mkdtemp(prefix=f"vocab_{job_id}_")

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
        cw = positions[0][2] - positions[0][0] if positions else 306
        W,H = 1080,1920
        tmp_img = Image.new("RGB", (W,H))
        tmp_draw = ImageDraw.Draw(tmp_img)
        ef, vf, en_top, std_eh, vi_top, std_vh = get_fonts_and_metrics(vocab, cw, cfg, tmp_draw)

        # Generate TTS
        audio_paths = []
        for i,(en,vi) in enumerate(vocab):
            ep = os.path.join(tmp,f"w{i:03d}_en.mp3")
            gTTS(en.replace("/"," "), lang="en", tld=req.voice_accent).save(ep)
            audio_paths.append(ep)

        temp_videos = []

        # Intro
        intro_img = render_frame(vocab,positions,-1,cfg)
        intro_path = os.path.join(tmp, "intro.png")
        intro_img.save(intro_path)
        intro = ImageClip(intro_path).with_duration(1.0)
        intro_mp4 = os.path.join(tmp, "intro.mp4")
        intro.write_videofile(intro_mp4, fps=30, codec="libx264", preset="ultrafast", logger=None)
        intro.close()
        temp_videos.append(intro_mp4)

        for i,(en,vi) in enumerate(vocab):
            ep = audio_paths[i]
            
            # The background frame (missing the active word)
            bg_img = render_frame(vocab, positions, active_idx=i, cfg=cfg, skip_idx=i)
            bg_path = os.path.join(tmp, f"bg_{i}.png")
            bg_img.save(bg_path)
            bg_clip = ImageClip(bg_path)
            
            # The active word cell
            pos = positions[i]
            x1, y1, x2, y2 = pos
            cell_w = x2 - x1
            cell_h = y2 - y1
            cx_abs = x1 + cell_w/2
            cy_abs = y1 + cell_h/2

            word_img = render_word_cell((en, vi), pos, cfg, ef, vf, en_top, std_eh, vi_top, std_vh, cw)
            word_path = os.path.join(tmp, f"word_{i}.png")
            word_img.save(word_path)
            arr = np.array(word_img)
            rgb = arr[:, :, :3]
            mask = arr[:, :, 3] / 255.0
            word_clip = ImageClip(rgb).with_mask(ImageClip(mask, is_mask=True))
            
            # Dynamic zoom animation func
            def make_scale(t):
                # Pop out quickly to 1.15x, then settle back to 1.0x
                if t < 0.15:
                    return 1.0 + (t/0.15) * 0.15
                elif t < 0.3:
                    return 1.15 - ((t-0.15)/0.15) * 0.15
                return 1.0
            
            # We capture local copies of the variables for the lambda functions
            def make_pos_func(cx, cy, cw_val, ch_val):
                def pos_func(t):
                    s = make_scale(t)
                    return (cx - (cw_val*s)/2, cy - (ch_val*s)/2)
                return pos_func
                
            animated_word = word_clip.resized(make_scale).with_position(make_pos_func(cx_abs, cy_abs, cw, cell_h))
            
            ea    = AudioFileClip(ep)
            s1    = AudioClip(lambda t: [0,0], duration=0.3)
            s2    = AudioClip(lambda t: [0,0], duration=0.8)
            audio = concatenate_audioclips([s1,ea,s2])
            
            composite = CompositeVideoClip([bg_clip, animated_word]).with_duration(audio.duration)
            composite = composite.with_audio(audio)
            
            word_mp4 = os.path.join(tmp, f"word_{i}.mp4")
            composite.write_videofile(
                word_mp4, fps=30, codec="libx264", audio_codec="aac",
                temp_audiofile=os.path.join(tmp, f"temp-audio-{i}.m4a"),
                preset="ultrafast", threads=2, remove_temp=True, logger=None
            )
            composite.close()
            bg_clip.close()
            word_clip.close()
            ea.close()
            temp_videos.append(word_mp4)

        # Outro
        outro_img = render_frame(vocab,positions,-1,cfg)
        outro_path = os.path.join(tmp, "outro.png")
        outro_img.save(outro_path)
        outro = ImageClip(outro_path).with_duration(1.5)
        outro_mp4 = os.path.join(tmp, "outro.mp4")
        outro.write_videofile(outro_mp4, fps=30, codec="libx264", preset="ultrafast", logger=None)
        outro.close()
        temp_videos.append(outro_mp4)

        # Final concatenation
        clips_to_concat = [VideoFileClip(p) for p in temp_videos]
        out_path = os.path.join(tmp, "output.mp4")
        final    = concatenate_videoclips(clips_to_concat, method="chain")
        final.write_videofile(
            out_path, fps=30, codec="libx264", audio_codec="aac",
            temp_audiofile=os.path.join(tmp, "temp-audio-final.m4a"),
            preset="ultrafast", threads=2, remove_temp=True, logger=None
        )
        final.close()
        for c in clips_to_concat:
            c.close()
        final.close()

        # Move to /tmp root so we can cleanup the dir but keep file
        result_path = f"/tmp/vocabvideo_{job_id}.mp4"
        shutil.copy(out_path, result_path)
        shutil.rmtree(tmp)

        background_tasks.add_task(os.remove, result_path)
        return FileResponse(
            result_path,
            media_type="video/mp4",
            filename=f"Vocabulary_Video.mp4",
        )

    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"detail": str(e)}, headers={"Access-Control-Allow-Origin": "*"})

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
