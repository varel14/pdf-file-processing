from pdf2image import convert_from_path
from surya.detection import DetectionPredictor
from surya.recognition import RecognitionPredictor

# Load models
detector = DetectionPredictor()
recognizer = RecognitionPredictor()

# Convert PDF → images
images = convert_from_path("document.pdf")

all_text = []

for image in images:
    # Detect text regions
    detections = detector([image])[0]

    # Recognize text
    lines = recognizer([image], [detections])[0]

    for line in lines:
        all_text.append(line.text)

# Print result
print("\n".join(all_text))