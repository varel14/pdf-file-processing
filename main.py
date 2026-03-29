import boto3
import easyocr
import ollama
import json
from pdf2image import convert_from_bytes
from io import BytesIO

R2_CONFIG = {
  "account_id": "b6c7083b2dda14cf990b9f8a3807e72d",
  "access_key": "d29ad6a70b9c8e139bcdadd704712473",
  "secret_key": "78ea3942a5d9699851e1a242f68b56221ec6dca21dfac45f509b0658af20914f",
  "bucket_name": "materials",
  "endpoint_url": "https://b6c7083b2dda14cf990b9f8a3807e72d.r2.cloudflarestorage.com"
}

s3 = boto3.client(
  service_name="s3",
  endpoint_url=R2_CONFIG["endpoint_url"],
  aws_access_key_id=R2_CONFIG["access_key"],
  aws_secret_access_key=R2_CONFIG["secret_key"],
  region_name="auto"
)

reader = easyocr.Reader(['fr', 'en'])

def process_files():
  response = s3.list_objects_v2(Bucket=R2_CONFIG["bucket_name"], Delimiter='/')
  
  if 'Contents' not in response:
    print("Aucun fichier trouvé.")
    return

  for obj in response['Contents']:
    file_key = obj['Key']
    if not file_key.lower().endswith('.pdf'):
        continue
        
    print(f"--- Traitement de : {file_key} ---")
    
    # Téléchargement en mémoire
    file_obj = s3.get_object(Bucket=R2_CONFIG["bucket_name"], Key=file_key)
    pdf_content = file_obj['Body'].read()
    
    # OCR sur la première page (souvent suffisante pour l'en-tête)
    images = convert_from_bytes(pdf_content, first_page=1, last_page=1)
    # Conversion de l'image PIL en bytes pour EasyOCR
    img_byte_arr = BytesIO()
    images[0].save(img_byte_arr, format='JPEG')
    
    ocr_results = reader.readtext(img_byte_arr.getvalue(), detail=0)
    raw_text = " ".join(ocr_results)

    print(f"Données extraites : {raw_text}")

    # 3. Extraction via LLM local (Ollama)
    extracted_data = extract_metadata_local(raw_text)
    
    print(f"Données extraites : {json.dumps(extracted_data, indent=2, ensure_ascii=False)}")
    break
    # # 4. Classification (Optionnel : déplacer le fichier)
    # classify_file_on_r2(file_key, extracted_data)

def extract_metadata_local(text):
  input_text = text[:2500] 
  
  prompt = f"""
  Analyse le texte d'un examen et extrait les informations en JSON pur.
  Champs requis :
  - education_level: (ex: Terminale, Première, Troisièmey)
  - exam_type: (ex: Baccalauréat, Probatoire, BEPC, Partiel, etc...)
  - year: (ex: 2023)
  - school_name: (nom de l'établissement ou null)
  - discipline: (ex: Mathématiques, Physique, Histoire)
  - serie: (Spécialité ex: Série A, C, D, TI, SES, G, ou null si non applicable)
  - language: (Si examen de langue ou série A, précise: Espagnol, Allemand, Chinois, Italien, etc., sinon null)

  Texte de l'examen :
  {input_text}

  Réponds uniquement avec le bloc JSON.
  """
  
  try:
    response = ollama.generate(model='llama3.2', prompt=prompt)
    raw_response = response['response'].strip()
    
    # Nettoyage des balises markdown si le LLM en ajoute
    if "```json" in raw_response:
      raw_response = raw_response.split("```json")[1].split("```")[0].strip()
    elif "```" in raw_response:
      raw_response = raw_response.split("```")[1].strip()
        
    return json.loads(raw_response)
  except Exception as e:
    print(f"❌ Erreur lors de l'extraction par LLM : {e}")


if __name__ == "__main__":
  process_files()