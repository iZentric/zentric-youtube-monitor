"""Expresii faciale din cameră (MediaPipe FaceLandmarker) → blendshape-uri pentru pngtuber.

Numele returnate sunt cele standard ARKit/MediaPipe (mouthSmileLeft, jawOpen, browInnerUp...),
adică exact cele din states.izentric.json. Modelul (~3 MB) se descarcă o singură dată.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
MODEL_DIR = Path(__file__).parent / "models"


def ensure_model(path: Path | None = None) -> Path:
    """Drumul către model; îl descarcă dacă lipsește."""
    target = Path(path) if path else MODEL_DIR / "face_landmarker.task"
    if target.exists() and target.stat().st_size > 100_000:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"descarc modelul de expresii în {target} ...")
    urllib.request.urlretrieve(MODEL_URL, target)
    return target


class FaceSource:
    """Citește blendshape-urile din camera video. Fără cameră nu are rost să pornească."""

    def __init__(self, model_path: str | None = None, camera: int = 0):
        self.model_path = ensure_model(Path(model_path) if model_path else None)
        self.camera = camera
        self._landmarker = None
        self._capture = None
        self._last: dict[str, float] = {}

    def start(self) -> "FaceSource":
        import cv2
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        self._cv2 = cv2
        self._mp = mp
        options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(self.model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=True,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)
        self._capture = cv2.VideoCapture(self.camera)
        if not self._capture.isOpened():
            raise RuntimeError(f"camera {self.camera} nu răspunde")
        return self

    def update(self) -> dict[str, float]:
        """Un cadru: {nume blendshape: 0..1}. Întoarce ultima valoare dacă citirea eșuează."""
        ok, frame = self._capture.read()
        if not ok:
            return self._last
        rgb = self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(image, int(self._cv2.getTickCount() / self._cv2.getTickFrequency() * 1000))
        if not result.face_blendshapes:
            self._last = {}
            return self._last
        self._last = {category.category_name: category.score for category in result.face_blendshapes[0]}
        return self._last

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
        if self._landmarker is not None:
            self._landmarker.close()
