import subprocess
import imageio_ffmpeg
ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

# create test mp3
subprocess.run([ffmpeg_exe, "-y", "-f", "lavfi", "-i", "sine=f=1000:d=1", "-c:a", "libmp3lame", "test.mp3"], check=True)

# delay by 300ms, pad end, take 2.1s total (0.3 + 1.0 + 0.8)
subprocess.run([ffmpeg_exe, "-y", "-i", "test.mp3", "-filter_complex", "adelay=300|300,apad", "-t", "2.1", "out.aac"], check=True)

# check duration of out.aac
res = subprocess.run([ffmpeg_exe, "-i", "out.aac", "-f", "null", "-"], capture_output=True, text=True)
print([line for line in res.stderr.split('\n') if 'Duration' in line])
