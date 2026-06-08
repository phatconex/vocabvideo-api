from moviepy import *
import numpy as np
import os
import subprocess

def test():
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    def make_silence(t):
        if hasattr(t, '__len__'):
            return np.zeros((len(t), 2))
        return np.zeros(2)

    c1 = ImageClip(np.zeros((100,100,3), dtype=np.uint8)).with_duration(1.0)
    c1 = c1.with_audio(AudioClip(make_silence, duration=1.0))
    c1.write_videofile("t1.mp4", fps=30, preset="ultrafast", audio_codec="aac", logger=None)
    
    c2 = ImageClip(np.ones((100,100,3), dtype=np.uint8)*255).with_duration(1.0)
    c2 = c2.with_audio(AudioClip(make_silence, duration=1.0))
    c2.write_videofile("t2.mp4", fps=30, preset="ultrafast", audio_codec="aac", logger=None)
    
    with open("list.txt", "w") as f:
        f.write("file 't1.mp4'\n")
        f.write("file 't2.mp4'\n")
        
    cmd = [ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy", "t_final.mp4"]
    subprocess.run(cmd, check=True)
    print("DONE")

test()
