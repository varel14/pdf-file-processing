from pdf2image import convert_from_path
from surya.ocr import run_ocr

# Convert PDF to images
images = convert_from_path("document.pdf")

# Run OCR
results = run_ocr(images)

# Print extracted text
for page in results:
    print(page.text)