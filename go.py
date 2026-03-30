from pdf2image import convert_from_path
from paddleocr import PaddleOCR

# Init OCR (CPU)
ocr = PaddleOCR(
  use_doc_orientation_classify=False,
  use_textline_orientation=False,
  use_doc_unwarping=False,
  lang='en'
)

# Convert PDF → images
images = convert_from_path("document.pdf", dpi=150)

all_text = []

for image in images:
    result = ocr.ocr(image, cls=True)

    for line in result[0]:
        text = line[1][0]
        all_text.append(text)

print("\n".join(all_text))