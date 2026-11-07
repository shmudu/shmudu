"""ClipSuite: turn long videos into captioned vertical shorts.

Pipeline: yt-dlp -> Whisper -> highlight picking -> FFmpeg render,
with hand-offs to Remotion, HyperFrames, DaVinci Resolve, ChatCut and Wan2GP.
"""

__version__ = "0.1.0"
