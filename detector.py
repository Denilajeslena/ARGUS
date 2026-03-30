import os
from functools import lru_cache

from ultralytics import YOLO

DEFAULT_MODEL_PATH = "yolov8m.pt"


@lru_cache(maxsize=2)
def get_model(model_path=DEFAULT_MODEL_PATH):
    """Load and cache YOLO models with automatic recovery from corrupt local files."""
    try:
        return YOLO(model_path)
    except Exception:
        if os.path.exists(model_path):
            os.remove(model_path)
        return YOLO(model_path)


def detect(frame, model_path=DEFAULT_MODEL_PATH, conf=0.3, imgsz=640, classes=None):
    """Run YOLO inference and return Ultralytics result objects."""
    model = get_model(model_path)
    results = model.predict(
        source=frame,
        conf=conf,
        imgsz=imgsz,
        classes=classes,
        verbose=False,
    )
    return results