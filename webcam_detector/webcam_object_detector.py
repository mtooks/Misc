import cv2
import torch
from ultralytics import YOLO
import time
import numpy as np

def main():
    # Check if CUDA is available and set device accordingly
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Using device: {device}")
    
    if device == 'cuda':
        # Get GPU information
        gpu_name = torch.cuda.get_device_name(0)
        print(f"GPU: {gpu_name}")
    
    # Load YOLO model - will download if not already present
    print("Loading YOLO model...")
    model = YOLO('yolov8n.pt')  # Using the nano model, can use 's', 'm', 'l', or 'x' for larger models
    
    # Access webcam
    print("Initializing webcam...")
    cap = cv2.VideoCapture(0)  # Use 0 for default webcam
    
    # Check if webcam is opened successfully
    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return
    
    # Get webcam resolution
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Webcam resolution: {width}x{height}")
    
    # Initialize FPS calculation variables
    fps = 0
    frame_count = 0
    start_time = time.time()
    
    print("Starting object detection. Press 'q' to quit.")
    
    while True:
        # Read frame from webcam
        ret, frame = cap.read()
        
        if not ret:
            print("Error: Failed to grab frame.")
            break
            
        # Perform object detection
        results = model(frame, device=device)
        
        # Process results
        for result in results:
            boxes = result.boxes.cpu().numpy()
            
            # Draw bounding boxes and labels
            for box in boxes:
                # Get box coordinates
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                
                # Get class and confidence
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                
                # Get class name
                cls_name = result.names[cls_id]
                
                # Draw bounding box
                color = (0, 255, 0)  # Green color for bounding box
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                
                # Create label
                label = f"{cls_name}: {conf:.2f}"
                
                # Put label slightly above the bounding box
                cv2.putText(frame, label, (x1, y1 - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        # Calculate and display FPS
        frame_count += 1
        elapsed_time = time.time() - start_time
        
        if elapsed_time >= 1.0:  # Update FPS every second
            fps = frame_count / elapsed_time
            frame_count = 0
            start_time = time.time()
            
        fps_text = f"FPS: {fps:.1f}"
        cv2.putText(frame, fps_text, (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        
        # Display the resulting frame
        cv2.imshow('YOLO Object Detection', frame)
        
        # Break the loop if 'q' is pressed
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    # Release resources
    cap.release()
    cv2.destroyAllWindows()
    
if __name__ == "__main__":
    main()
