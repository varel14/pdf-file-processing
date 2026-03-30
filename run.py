from pdf2image import convert_from_path
from surya.detection import DetectionPredictor
from surya.recognition import RecognitionPredictor
from surya.foundation import FoundationPredictor

# Load models
foundation = FoundationPredictor()
detector = DetectionPredictor()
recognizer = RecognitionPredictor(foundation)

# Convert PDF → images
images = convert_from_path("document.pdf")

all_text = []

for image in images:
    lines = recognizer([image], det_predictor=detector)[0]

    for line in lines:
        text = line[0]
        all_text.append(text)

# Print result
print("\n".join(all_text))