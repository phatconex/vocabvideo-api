from moviepy import *
import numpy as np

def test():
    # create two 1s videos
    c1 = ImageClip(np.zeros((100,100,3), dtype=np.uint8)).with_duration(1.0)
    c1.write_videofile("t1.mp4", fps=30, preset="ultrafast", logger=None)
    
    c2 = ImageClip(np.ones((100,100,3), dtype=np.uint8)*255).with_duration(1.0)
    c2.write_videofile("t2.mp4", fps=30, preset="ultrafast", logger=None)
    
    clips = [VideoFileClip("t1.mp4"), VideoFileClip("t2.mp4")]
    final = concatenate_videoclips(clips, method="chain")
    final.write_videofile("t_final.mp4", fps=30, preset="ultrafast", logger=None)
    
test()
