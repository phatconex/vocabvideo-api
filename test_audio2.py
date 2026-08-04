import subprocess
import imageio_ffmpeg
from gtts import gTTS

ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

# 1. Create MP3
gTTS("Hello World", lang="en").save("test.mp3")

# 2. Convert to WAV
subprocess.run([ffmpeg_exe, "-y", "-i", "test.mp3", "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", "test.wav"], check=True)

# 3. Create Silence WAVs
subprocess.run([ffmpeg_exe, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "0.3", "-c:a", "pcm_s16le", "s1.wav"], check=True)
subprocess.run([ffmpeg_exe, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "0.8", "-c:a", "pcm_s16le", "s2.wav"], check=True)

# 4. Concat
with open("list.txt", "w") as f:
    f.write("file 's1.wav'\n")
    f.write("file 'test.wav'\n")
    f.write("file 's2.wav'\n")
subprocess.run([ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy", "out.wav"], check=True)

# 5. Check out.wav duration and volume
res = subprocess.run([ffmpeg_exe, "-i", "out.wav", "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
print("--- OUTPUT ---")
print([line for line in res.stderr.split('\n') if 'Duration' in line or 'mean_volume' in line])
