"""
=====================================
 VOCAB VIDEO GENERATOR
 Tạo video từ vựng tiếng Anh tự động
=====================================

CÁCH DÙNG:
1. Cài thư viện: pip3.11 install pillow moviepy gtts
2. Chỉnh CONFIG bên dưới (màu, font, tốc độ...)
3. Tạo file vocab.csv theo mẫu
4. Chạy: python3.11 vocab_video_generator.py

OUTPUT: video_output.mp4
"""

import csv
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS
from moviepy import *
import numpy as np

# ============================================================
#  ⚙️  CONFIG - Chỉnh tất cả settings ở đây
# ============================================================
CONFIG = {
    # --- File paths ---
    "input_csv":        "vocab.csv",          # File CSV đầu vào
    "output_video":     "video_output.mp4",   # Video output
    "temp_dir":         "temp_assets",        # Thư mục chứa file tạm

    # --- Video dimensions ---
    "video_width":      1080,                 # Chiều rộng (px)
    "video_height":     1920,                 # Chiều cao (portrait 9:16)

    # --- Background ---
    "bg_color":         (240, 248, 255),      # Màu nền video (light blue)

    # --- Card style ---
    "card_bg_color":    (100, 181, 246),      # Màu nền card (xanh dương)
    "card_radius":      28,                   # Bo góc card
    "card_padding_x":   18,                   # Padding ngang trong card
    "card_padding_y":   14,                   # Padding dọc trong card
    "card_shadow":      True,                 # Bật/tắt shadow cho card

    # --- Text style ---
    "en_text_color":    (255, 255, 255),      # Màu chữ tiếng Anh
    "vi_text_color":    (255, 255, 255),      # Màu chữ tiếng Việt
    "en_font_size":     52,                   # Cỡ chữ tiếng Anh (bold)
    "vi_font_size":     38,                   # Cỡ chữ tiếng Việt

    # Highlight khi card đang được đọc
    "highlight_bg":     (255, 213, 79),       # Màu card khi highlight (vàng)
    "highlight_en":     (33, 33, 33),         # Màu chữ EN khi highlight
    "highlight_vi":     (33, 33, 33),         # Màu chữ VI khi highlight

    # --- Grid layout ---
    "cols":             3,                    # Số cột
    "grid_margin_x":    40,                   # Margin trái/phải của grid
    "grid_margin_top":  200,                  # Khoảng cách từ top xuống grid
    "grid_gap_x":       20,                   # Khoảng cách ngang giữa cards
    "grid_gap_y":       24,                   # Khoảng cách dọc giữa cards

    # --- Hand pointer ---
    "hand_emoji":       "👆",                 # Emoji bàn tay
    "hand_size":        80,                   # Kích thước emoji bàn tay
    "hand_offset_x":    10,                   # Offset X của bàn tay so với card
    "hand_offset_y":    -20,                  # Offset Y (âm = lên trên)

    # --- Title ---
    "title_text":       "Family Members",     # Tiêu đề video (đổi theo chủ đề)
    "title_color":      (33, 33, 33),
    "title_font_size":  72,
    "title_y":          80,                   # Vị trí Y của title

    # --- Timing ---
    "pause_before_en":  0.3,   # Dừng trước khi đọc EN (giây)
    "pause_between":    0.2,   # Dừng giữa EN và VI
    "pause_after_vi":   0.5,   # Dừng sau khi đọc VI
    "intro_duration":   1.0,   # Thời gian hiện layout trước khi bắt đầu đọc

    # --- FPS ---
    "fps":              30,
}

# ============================================================
#  📁  SAMPLE CSV
# ============================================================
SAMPLE_CSV = """English,Vietnamese
Family,Gia đình
Father,Bố
Mother,Mẹ
Son,Con trai
Daughter,Con gái
Brother,Anh/Em trai
Sister,Chị/Em gái
Uncle,Chú/cậu/bác trai
Aunt,Cô/dì/bác gái
Nephew,Cháu trai
Niece,Cháu gái
Cousin,Anh/Chị em họ
Grandfather,Ông
Grandmother,Bà
"""

# ============================================================
#  🎨  UTILS - Vẽ card bo góc
# ============================================================
def draw_rounded_rect(draw, xy, radius, fill, shadow=False):
    x1, y1, x2, y2 = xy
    if shadow:
        sx, sy = 4, 4
        shadow_color = tuple(max(0, c - 60) for c in fill[:3])
        _draw_rounded_rect_solid(draw, (x1+sx, y1+sy, x2+sx, y2+sy), radius, shadow_color + (120,))
    _draw_rounded_rect_solid(draw, (x1, y1, x2, y2), radius, fill)

def _draw_rounded_rect_solid(draw, xy, radius, fill):
    x1, y1, x2, y2 = xy
    r = radius
    draw.rectangle([x1 + r, y1, x2 - r, y2], fill=fill)
    draw.rectangle([x1, y1 + r, x2, y2 - r], fill=fill)
    draw.ellipse([x1, y1, x1 + 2*r, y1 + 2*r], fill=fill)
    draw.ellipse([x2 - 2*r, y1, x2, y1 + 2*r], fill=fill)
    draw.ellipse([x1, y2 - 2*r, x1 + 2*r, y2], fill=fill)
    draw.ellipse([x2 - 2*r, y2 - 2*r, x2, y2], fill=fill)

def get_font(size, bold=False):
    """Load font macOS, fallback về Pillow default"""
    font_paths = []
    if bold:
        font_paths = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ]
    else:
        font_paths = [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
    for path in font_paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)

# ============================================================
#  🖼️  RENDER FRAME
# ============================================================
def render_frame(vocab_list, card_positions, active_idx, cfg):
    W, H = cfg["video_width"], cfg["video_height"]
    img = Image.new("RGB", (W, H), cfg["bg_color"])
    draw = ImageDraw.Draw(img, "RGBA")

    # Vẽ title
    title_font = get_font(cfg["title_font_size"], bold=True)
    title_bbox = draw.textbbox((0, 0), cfg["title_text"], font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    draw.text(
        ((W - title_w) // 2, cfg["title_y"]),
        cfg["title_text"],
        font=title_font,
        fill=cfg["title_color"]
    )

    en_font = get_font(cfg["en_font_size"], bold=True)
    vi_font = get_font(cfg["vi_font_size"], bold=False)

    for i, ((en, vi), (x1, y1, x2, y2)) in enumerate(zip(vocab_list, card_positions)):
        is_active = (i == active_idx)

        bg       = cfg["highlight_bg"]  if is_active else cfg["card_bg_color"]
        en_color = cfg["highlight_en"]  if is_active else cfg["en_text_color"]
        vi_color = cfg["highlight_vi"]  if is_active else cfg["vi_text_color"]

        draw_rounded_rect(draw, (x1, y1, x2, y2), cfg["card_radius"], bg, shadow=cfg["card_shadow"])

        card_cx = x1 + (x2 - x1) // 2
        card_cy = y1 + (y2 - y1) // 2

        en_bbox = draw.textbbox((0, 0), en, font=en_font)
        en_h = en_bbox[3] - en_bbox[1]
        en_w = en_bbox[2] - en_bbox[0]

        vi_bbox = draw.textbbox((0, 0), vi, font=vi_font)
        vi_h = vi_bbox[3] - vi_bbox[1]
        vi_w = vi_bbox[2] - vi_bbox[0]

        gap = 6
        total_h = en_h + gap + vi_h
        en_y = card_cy - total_h // 2
        vi_y = en_y + en_h + gap

        draw.text((card_cx - en_w // 2, en_y), en, font=en_font, fill=en_color)
        draw.text((card_cx - vi_w // 2, vi_y), vi, font=vi_font, fill=vi_color)

        # Bàn tay pointer
        if is_active:
            hand_font = get_font(cfg["hand_size"])
            hx = x1 + cfg["hand_offset_x"]
            hy = y1 + cfg["hand_offset_y"] - cfg["hand_size"]
            draw.text((hx, hy), cfg["hand_emoji"], font=hand_font, embedded_color=True)

    return img

# ============================================================
#  📐  CARD POSITIONS
# ============================================================
def calculate_card_positions(vocab_list, cfg):
    W    = cfg["video_width"]
    cols = cfg["cols"]
    mx   = cfg["grid_margin_x"]
    gx   = cfg["grid_gap_x"]
    gy   = cfg["grid_gap_y"]
    top  = cfg["grid_margin_top"]

    card_w = (W - 2 * mx - (cols - 1) * gx) // cols
    card_h = cfg["en_font_size"] + cfg["vi_font_size"] + cfg["card_padding_y"] * 3 + 10

    positions = []
    for i in range(len(vocab_list)):
        row = i // cols
        col = i % cols
        x1 = mx + col * (card_w + gx)
        y1 = top + row * (card_h + gy)
        positions.append((x1, y1, x1 + card_w, y1 + card_h))

    return positions, card_h

# ============================================================
#  🔊  TTS - dùng gTTS (Google TTS, ổn định, không cần token)
# ============================================================
def generate_tts(text, lang, output_path):
    """
    Tạo file audio bằng gTTS
    - lang="en" cho tiếng Anh
    - lang="vi" cho tiếng Việt
    - Dấu "/" được thay bằng ", " để đọc tự nhiên hơn
    """
    clean_text = text.replace("/", ", ")
    tts = gTTS(text=clean_text, lang=lang, slow=False)
    tts.save(output_path)

def generate_all_audio(vocab_list, cfg, temp_dir):
    """Generate audio MP3 cho toàn bộ danh sách từ vựng"""
    print("🔊 Generating TTS audio...")
    audio_paths = []

    for i, (en, vi) in enumerate(vocab_list):
        en_path = os.path.join(temp_dir, f"word_{i:03d}_en.mp3")
        vi_path = os.path.join(temp_dir, f"word_{i:03d}_vi.mp3")

        print(f"   [{i+1}/{len(vocab_list)}] {en} / {vi}")
        generate_tts(en, "en", en_path)   # Đọc tiếng Anh
        generate_tts(vi, "vi", vi_path)   # Đọc tiếng Việt

        audio_paths.append((en_path, vi_path))

    return audio_paths

# ============================================================
#  🎬  BUILD VIDEO
# ============================================================
def get_audio_duration(path):
    clip = AudioFileClip(path)
    dur  = clip.duration
    clip.close()
    return dur

def build_video(vocab_list, card_positions, audio_paths, cfg):
    print("\n🎬 Building video...")
    fps   = cfg["fps"]
    clips = []

    # Intro: hiện toàn bộ layout 1 giây trước khi bắt đầu đọc
    intro_img  = render_frame(vocab_list, card_positions, -1, cfg)
    intro_clip = ImageClip(np.array(intro_img), duration=cfg["intro_duration"])
    clips.append(intro_clip)

    for i, (en, vi) in enumerate(vocab_list):
        en_path, vi_path = audio_paths[i]

        en_dur = get_audio_duration(en_path)
        vi_dur = get_audio_duration(vi_path)

        pb = cfg["pause_before_en"]
        pm = cfg["pause_between"]
        pa = cfg["pause_after_vi"]
        total_dur = pb + en_dur + pm + vi_dur + pa

        # Frame highlight card hiện tại
        frame_img  = render_frame(vocab_list, card_positions, i, cfg)
        img_clip   = ImageClip(np.array(frame_img), duration=total_dur)

        # Ghép audio: silence + EN + silence + VI + silence
        silence_before = AudioClip(lambda t: [0, 0], duration=pb,  fps=44100)
        en_audio       = AudioFileClip(en_path)
        silence_mid    = AudioClip(lambda t: [0, 0], duration=pm,  fps=44100)
        vi_audio       = AudioFileClip(vi_path)
        silence_after  = AudioClip(lambda t: [0, 0], duration=pa,  fps=44100)

        word_audio = concatenate_audioclips([silence_before, en_audio, silence_mid, vi_audio, silence_after])
        word_clip  = img_clip.with_audio(word_audio)
        clips.append(word_clip)

        print(f"   ✅ [{i+1}/{len(vocab_list)}] {en}: {total_dur:.1f}s")

    # Outro: hiện lại toàn bộ không highlight
    outro_img  = render_frame(vocab_list, card_positions, -1, cfg)
    outro_clip = ImageClip(np.array(outro_img), duration=1.5)
    clips.append(outro_clip)

    print("\n🔗 Concatenating clips...")
    final = concatenate_videoclips(clips, method="compose")

    print(f"💾 Exporting → {cfg['output_video']}...")
    final.write_videofile(
        cfg["output_video"],
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile="temp_audio.m4a",
        remove_temp=True,
        logger=None
    )

    for clip in clips:
        clip.close()
    final.close()

# ============================================================
#  🚀  MAIN
# ============================================================
def load_vocab(csv_path):
    vocab = []
    with open(csv_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            en = row.get("English", "").strip()
            vi = row.get("Vietnamese", "").strip()
            if en and vi:
                vocab.append((en, vi))
    return vocab

def main():
    cfg      = CONFIG
    temp_dir = cfg["temp_dir"]
    os.makedirs(temp_dir, exist_ok=True)

    # Tạo CSV mẫu nếu chưa có
    if not os.path.exists(cfg["input_csv"]):
        with open(cfg["input_csv"], "w", encoding="utf-8") as f:
            f.write(SAMPLE_CSV.strip())
        print(f"📄 Đã tạo file mẫu '{cfg['input_csv']}'. Hãy chỉnh nội dung rồi chạy lại.")
        return

    vocab_list = load_vocab(cfg["input_csv"])
    print(f"📚 Loaded {len(vocab_list)} words from {cfg['input_csv']}")

    card_positions, _ = calculate_card_positions(vocab_list, cfg)
    audio_paths       = generate_all_audio(vocab_list, cfg, temp_dir)

    build_video(vocab_list, card_positions, audio_paths, cfg)

    total_dur = sum(
        get_audio_duration(p) + get_audio_duration(q)
        + cfg["pause_before_en"] + cfg["pause_between"] + cfg["pause_after_vi"]
        for p, q in audio_paths
    ) + cfg["intro_duration"] + 1.5

    print(f"\n✅ Done! Video saved: {cfg['output_video']}  (~{total_dur:.0f}s)")

    import shutil
    shutil.rmtree(temp_dir)
    print("🧹 Cleaned up temp files")

if __name__ == "__main__":
    main()
