# guide_module.py
# Lean centroid-based autoguider using the science-cam preview stream.

import base64
import io
import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np
import requests

from utilities.config import RASPBERRY_PI_IP
from utilities.logger import emit_log
from modules.mount_module import MountControl

_socketio = None  # set via set_socketio()


def set_socketio(instance):
    """Attach global socketio for overlay + status emits."""
    global _socketio
    _socketio = instance


@dataclass
class GuiderConfig:
    # Frame source
    url: str = None  # filled from RASPBERRY_PI_IP if None
    timeout_s: float = 1.0
    target_fps: float = 5.0
    downscale_width: int = 480  # speed + stable overlay size

    # Detection (bright-disk centroid)
    blur_ksize: int = 5
    min_contour_area: int = 80      # px; ignore speckles
    lock_radius_px: int = 8         # inside this, consider "locked"
    lock_hold_frames: int = 10      # frames required to declare/keep lock
    deadband_px: int = 5            # no corrections inside this radius

    # Correction mapping: pixels -> pulse duration
    kp_ms_per_px: float = 4.0       # 4 ms per pixel as a starting point
    min_pulse_ms: int = 40
    max_pulse_ms: int = 600
    min_axis_interval_ms: int = 120 # refractory per-axis between pulses

    # JPEG overlay quality
    jpeg_quality: int = 70


class AutoGuider:
    def __init__(self, mount: MountControl, config: Optional[GuiderConfig] = None):
        self.mount = mount
        self.cfg = config or GuiderConfig()
        if self.cfg.url is None:
            self.cfg.url = f"http://{RASPBERRY_PI_IP}:8082/fc_preview.jpg"

        self._running = False
        self._thread: Optional[threading.Thread] = None

        # status
        self._fps = 0.0
        self._locked = False
        self._lock_streak = 0
        self._last_overlay_b64 = None
        self._last_status = {
            "status": "IDLE",
            "fps": "--",
            "locked": False,
            "dx": "--",
            "dy": "--",
            "r":  "--",
        }

        # per-axis refractory to avoid spamming pulses
        self._last_pulse_time = {"ra": 0.0, "dec": 0.0}

    # ---------- public API ----------

    def start(self):
        if self._running:
            emit_log("[GUIDER] already running")
            return
        self._running = True
        emit_log(f"[GUIDER] starting (src={self.cfg.url})")
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        emit_log("[GUIDER] stop requested")

    def get_status(self):
        """Return last status dict (cheap) for one-shot poll."""
        return dict(self._last_status)

    # ---------- core loop ----------

    def _loop(self):
        tgt_dt = 1.0 / max(0.5, float(self.cfg.target_fps))
        t_last_fps = time.time()
        frames = 0

        while self._running:
            t0 = time.time()
            try:
                frame = self._fetch_frame()
                if frame is None:
                    self._update_status("NO_FRAME", None)
                else:
                    overlay, dx, dy, r, found = self._process_frame(frame)
                    self._push_overlay(overlay)

                    if found:
                        self._guide(dx, dy, r)
                    self._update_status("RUN" if found else "SEARCH", (dx, dy, r))

            except Exception as e:
                emit_log(f"[GUIDER] loop error: {e}")
                self._update_status("ERROR", None)

            # fps calc
            frames += 1
            if time.time() - t_last_fps >= 1.0:
                self._fps = frames / (time.time() - t_last_fps)
                t_last_fps = time.time()
                frames = 0

            # pace to target fps
            dt = time.time() - t0
            if dt < tgt_dt:
                time.sleep(tgt_dt - dt)

        self._update_status("IDLE", None)
        emit_log("[GUIDER] loop ended")

    # ---------- frame input ----------

    def _fetch_frame(self) -> Optional[np.ndarray]:
        r = requests.get(self.cfg.url, timeout=self.cfg.timeout_s)
        if r.status_code != 200:
            return None
        data = np.frombuffer(r.content, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            return None
        # downscale to fixed width
        h, w = img.shape[:2]
        if w > self.cfg.downscale_width:
            scale = self.cfg.downscale_width / float(w)
            img = cv2.resize(img, (self.cfg.downscale_width, int(h * scale)), interpolation=cv2.INTER_AREA)
        return img

    # ---------- detection + overlay ----------

    def _process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, Optional[float], Optional[float], Optional[float], bool]:
        h, w = frame.shape[:2]
        cx, cy = w // 2, h // 2

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self.cfg.blur_ksize > 1:
            gray = cv2.GaussianBlur(gray, (self._odd(self.cfg.blur_ksize), self._odd(self.cfg.blur_ksize)), 0)

        # Otsu threshold (bright disk)
        _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Largest contour
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best = None
        best_area = 0
        for c in contours:
            a = cv2.contourArea(c)
            if a > best_area and a >= self.cfg.min_contour_area:
                best = c
                best_area = a

        # draw crosshair (frame center)
        overlay = frame.copy()
        self._draw_crosshair(overlay, (cx, cy), (255, 128, 0), 11, 2)  # blue-ish center

        if best is None:
            # no sun found: render mask hint (optional)
            return self._encode_overlay(overlay), None, None, None, False

        M = cv2.moments(best)
        if M["m00"] == 0:
            return self._encode_overlay(overlay), None, None, None, False
        tx = int(M["m10"] / M["m00"])
        ty = int(M["m01"] / M["m00"])

        dx = tx - cx
        dy = ty - cy
        r = float(np.hypot(dx, dy))

        # draw detected centroid + error vector
        self._draw_crosshair(overlay, (tx, ty), (0, 0, 255), 11, 2)     # red = target centroid
        cv2.line(overlay, (cx, cy), (tx, ty), (0, 200, 0), 2)           # green = error vector
        cv2.circle(overlay, (cx, cy), self.cfg.lock_radius_px, (0, 170, 0), 1)  # lock ring

        return self._encode_overlay(overlay), float(dx), float(dy), r, True

    @staticmethod
    def _odd(n: int) -> int:
        return n if n % 2 else n + 1

    @staticmethod
    def _draw_crosshair(img, pt, color, size=9, thick=2):
        x, y = pt
        cv2.line(img, (x - size, y), (x + size, y), color, thick)
        cv2.line(img, (x, y - size), (x, y + size), color, thick)
        cv2.circle(img, (x, y), 2, color, -1)

    def _encode_overlay(self, img: np.ndarray) -> str:
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), int(self.cfg.jpeg_quality)]
        ok, enc = cv2.imencode(".jpg", img, encode_param)
        if not ok:
            return None
        b64 = base64.b64encode(enc.tobytes()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"

    def _push_overlay(self, overlay_b64: Optional[str]):
        self._last_overlay_b64 = overlay_b64
        if _socketio and overlay_b64:
            _socketio.emit("guiding_overlay", overlay_b64)

    # ---------- guidance ----------

    def _guide(self, dx: float, dy: float, r: float):
        # lock logic (purely for status)
        if r <= self.cfg.lock_radius_px:
            self._lock_streak = min(self._lock_streak + 1, self.cfg.lock_hold_frames)
        else:
            self._lock_streak = max(self._lock_streak - 1, 0)
        self._locked = self._lock_streak >= self.cfg.lock_hold_frames

        # deadband: no corrections
        if r <= self.cfg.deadband_px:
            return

        # map pixels to ms pulse
        ms = int(self.cfg.kp_ms_per_px * r)
        ms = max(self.cfg.min_pulse_ms, min(ms, self.cfg.max_pulse_ms))

        now = time.time()

        # RA correction (dx): if target is to the RIGHT (dx>0), we need to move RA EAST or WEST?
        # Without flips, assume: dx>0 => nudge EAST, dx<0 => nudge WEST.
        if abs(dx) > self.cfg.deadband_px:
            if (now - self._last_pulse_time["ra"]) * 1000.0 >= self.cfg.min_axis_interval_ms:
                ra_dir = "east" if dx > 0 else "west"
                self.mount.nudge(ra_dir, ms=ms, rate="solar")
                self._last_pulse_time["ra"] = now

        # DEC correction (dy): if target is BELOW center (dy>0), nudge SOUTH; above => NORTH.
        if abs(dy) > self.cfg.deadband_px:
            if (now - self._last_pulse_time["dec"]) * 1000.0 >= self.cfg.min_axis_interval_ms:
                dec_dir = "south" if dy > 0 else "north"
                self.mount.nudge(dec_dir, ms=ms, rate="solar")
                self._last_pulse_time["dec"] = now

    # ---------- status ----------

    def _update_status(self, state: str, err_tuple: Optional[Tuple[float, float, float]]):
        if err_tuple is None:
            dx = dy = r = None
        else:
            dx, dy, r = err_tuple

        status = {
            "status": state if self._running else "IDLE",
            "fps": round(self._fps, 2) if self._fps else "--",
            "locked": bool(self._locked),
            "dx": None if dx is None else round(float(dx), 1),
            "dy": None if dy is None else round(float(dy), 1),
            "r":  None if r  is None else round(float(r), 1),
        }
        self._last_status = status

        if _socketio:
            _socketio.emit("guiding_status", status)
