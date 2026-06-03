# Webcam Object Detection with YOLO

This script uses your webcam as video input and detects objects in real-time using the YOLO (You Only Look Once) model. It's optimized to take advantage of NVIDIA GPUs for faster inference.

## Requirements

- Python 3.7+
- PyTorch
- OpenCV
- Ultralytics YOLO package

## Setup Instructions

1. Install the required packages:

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
pip install opencv-python
pip install ultralytics
```

Note: The PyTorch installation command above is for CUDA 11.8. If you have a different CUDA version, check the [PyTorch website](https://pytorch.org/get-started/locally/) for the appropriate installation command.

2. Run the script:

```bash
python webcam_object_detector.py
```

## Usage

- The script will automatically use your default webcam (index 0).
- Press 'q' to quit the application.
- The script displays bounding boxes around detected objects along with their class names and confidence scores.
- FPS (Frames Per Second) is displayed in the top-left corner.

## GPU Acceleration

This script automatically uses your NVIDIA RTX 4090 if CUDA is available. The YOLO model will perform inference on the GPU for significantly better performance.

## Customization Options

- To use a different YOLO model size, modify the model loading line:
  - `model = YOLO('yolov8n.pt')` (nano - fastest, less accurate)
  - `model = YOLO('yolov8s.pt')` (small)
  - `model = YOLO('yolov8m.pt')` (medium)
  - `model = YOLO('yolov8l.pt')` (large)
  - `model = YOLO('yolov8x.pt')` (xlarge - slowest, most accurate)

- To use a different webcam, change the index in `cv2.VideoCapture(0)` to the appropriate device index.

## Troubleshooting

If you encounter any issues with the webcam, try changing the webcam index or checking your webcam permissions.
