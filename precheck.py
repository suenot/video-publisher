import subprocess

LIMIT_S = 900  # 15 min, the unverified-channel ceiling


def parse_ffprobe_duration(stdout):
    return float(stdout.strip())


def _default_runner(path):
    return subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nokey=1:noprint_wrappers=1", path],
        capture_output=True, text=True, check=True).stdout


def video_duration(path, runner=_default_runner):
    return parse_ffprobe_duration(runner(path))


def check(duration_s, verified, allow_long):
    if duration_s > LIMIT_S and not verified and not allow_long:
        return (False,
                f"Video is too long: {int(duration_s)}s (> {LIMIT_S}s / 15min) and "
                "the channel is not verified — YouTube will abandon processing. "
                "Verify the channel (youtube.com/verify) or pass --allow-long.")
    return (True, "")
