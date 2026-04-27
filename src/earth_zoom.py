"""Flagship Earth Zoom In scenario — tuned to match the Higgsfield reference.

Reference sample: https://higgsfield.ai/s/28TKrUxP9Bk
(og:image mp4 inspected on 2026-04-20)
    * duration: 8.06 s @ 24 fps (→ we request 8 s)
    * resolution: 834×1112 portrait (≈3:4)
    * pipeline: Earth from space → aerial city shot → the user's original
      photo is the FINAL frame, unchanged.

We replicate it as a DoP dual-frame render:
    start_image = pre-generated photorealistic Earth (Soul)
    end_image   = user's selfie
    motion      = "Earth Zoom Out" (the trained face→Earth trajectory, which
                  when keyframes are flipped renders Earth→face).
"""
from __future__ import annotations

from typing import Final

EARTH_ZOOM_OUT_MOTION_ID: Final[str] = "46fa79e3-efce-41e8-95bc-1dc5a1a30795"
EARTH_ZOOM_OUT_MOTION_NAME: Final[str] = "Earth Zoom Out"

# Aspect ratio and size for the pre-generated Earth background. Soul accepts
# string "WxH"; we use a portrait 3:4 frame so the Earth fills vertical.
EARTH_IMAGE_WIDTH_AND_HEIGHT: Final[str] = "1152x1536"  # 3:4 portrait, ~Soul sweet-spot
EARTH_IMAGE_QUALITY: Final[str] = "1080p"

# Soul prompt for generating a photorealistic Earth.
EARTH_SOUL_PROMPT: Final[str] = (
    "Photorealistic planet Earth seen from low orbit during golden hour. "
    "The curvature of the globe dominates the center of the frame. Deep "
    "black starfield background, sharp pinpoint stars. Continents "
    "(North America and the Americas) clearly visible in rich detail — "
    "brown mountain ranges, green forests, blue oceans, swirling white "
    "cumulus cloud systems, thin cyan atmosphere haze at the horizon. "
    "Soft rim sunlight from the left. IMAX-grade clarity, NASA reference "
    "photography, 8K, hyper-detailed, no text, no watermark, cinematic."
)

# DoP prompt for the canonical "Earth Zoom Out" motion.
#
# Important: the motion is trained for SUBJECT -> EARTH. We generate
# start=person, end=earth, then reverse the clip for Earth -> person.
#
# The middle leg (atmosphere / city / ground) is the hardest. We stress:
# * one continuous take, photoreal, sharp where altitude is still low
# * no surreal double-globe, tiny-planet, or abstract smeared tiles
# English tends to follow camera vocabulary reliably on this API.
EARTH_ZOOM_IN_DOP_PROMPT: Final[str] = (
    "Single continuous camera pullback from the subject, one long take, no "
    "cuts. After the first frames on the person, the camera gains altitude: "
    "first pass through a thin cloud layer, then a wide, photoreal, sharp "
    "aerial view of a real city and landscape — clear buildings, streets, "
    "parks, natural daylight, high detail, not painterly, not stylized, not "
    "a texture collage. The ground and urban leg must look like a real "
    "satellite or drone pass (stable perspective, no fisheye 'tiny planet', "
    "no second Earth globe in the frame). Then continue rising through haze to "
    "the black sky and end on a full photoreal Earth disk in space, matching "
    "the end keyframe. Smooth, coherent geography throughout."
)

# Slightly below max — reduces warping in the hard middle segment; raise if
# the zoom feels too weak (max 1.0 per API).
EARTH_ZOOM_OUT_MOTION_STRENGTH: Final[float] = 0.75

# If True, Higgsfield rewrites the prompt; can dilute the explicit "sharp city
# leg" instructions — keep False to stick to the text above.
EARTH_ZOOM_DOP_ENHANCE_PROMPT: Final[bool] = False

# Render parameters. Verified 2026-04-20 by side-by-side probing:
#
#   model         | output resolution      | output duration (any req.)
#   --------------|-----------------------|---------------------------
#   dop-lite      | 960x1280 (HD 3:4)     | 5.37 s @ 30 fps   ← BEST
#   dop-preview   | 816x1104 (SD 3:4)     | 5.37 s @ 30 fps
#   dop-turbo     | 816x1104 (SD 3:4)     | 5.37 s @ 30 fps
#
# DoP ignores `duration > 5` regardless of the requested value (always 5.37 s).
# The 8-second reference (https://higgsfield.ai/s/28TKrUxP9Bk) was rendered
# through Higgsfield's web UI on a different pipeline not exposed via this
# public API tier.  We therefore pin honest 5 s HD via dop-lite — the best
# quality the API can give us for this dual-frame Earth→face scenario.
DURATION_SECONDS: Final[int] = 5
ASPECT_RATIO: Final[str] = "3:4"
ASPECT_TO_WH_PORTRAIT: Final[tuple[int, int]] = (1152, 1536)
DOP_MODEL: Final[str] = "dop-lite"
