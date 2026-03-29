import logging
import time
import boto3
import easyocr
import ollama
import json
import sqlite3
import gc
import os
from pdf2image import convert_from_bytes
from io import BytesIO

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("processing.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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

conn = sqlite3.connect('examens_data.db')
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS extractions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        original_path TEXT,
        extracted_text TEXT,
        json_output TEXT,
        new_r2_path TEXT,
        proc_time_sec REAL
    )
''')
conn.commit()

logger.info("Initialisation de EasyOCR (chargement des modèles)...")
reader = easyocr.Reader(['fr', 'en'])

def extract_metadata_local(text):
    prompt = f"""
    Analyse ce texte d'examen et retourne un JSON pur (sans texte autour) :
    - education_level (ex: Terminale, Première, Troisième)
    - exam_type (ex: Baccalauréat, Probatoire, BEPC)
    - year (ex: 2023)
    - school_name (nom de l'école ou null)
    - discipline (Format: "Epreuve de [Nom de la matière]")
    - serie (Série A, C, D, TI, SES, etc.)
    - language (Espagnol, Allemand, Chinois, Italien, etc. ou null)

    Texte : {text[:2500]}
    """
    try:
        response = ollama.generate(model='llama3.2', prompt=prompt)
        
        res_text = response['response'].strip()
        if "```" in res_text:
            res_text = res_text.split("```")[1].replace("json", "").strip()
        return json.loads(res_text)
    except Exception as e:
      logger.error(f"Erreur parsing LLM: {e}")
      return None

def process_exam_files():
    try:
      response = s3.list_objects_v2(Bucket=R2_CONFIG["bucket_name"], Delimiter='/')
    except Exception as e:
      logger.error(f"Impossible de lister le bucket R2: {e}")
      return

    if 'Contents' not in response:
      logger.info("Aucun fichier PDF trouvé à la racine.")
      return

    for obj in response['Contents']:
      file_key = obj['Key']
      if not file_key.lower().endswith('.pdf'): 
        continue

      start_total = time.time()
      logger.info(f"--- Début du traitement : {file_key} ---")
      
      try:
        t0 = time.time()
        file_obj = s3.get_object(Bucket=R2_CONFIG["bucket_name"], Key=file_key)
        pdf_content = file_obj['Body'].read()
        logger.info(f"  [1/4] Download R2 fini en {time.time()-t0:.2f}s")
        
        t1 = time.time()
        images = convert_from_bytes(pdf_content, first_page=1, last_page=1)
        img_byte_arr = BytesIO()
        images[0].save(img_byte_arr, format='JPEG', quality=85)
        
        raw_text = " ".join(reader.readtext(img_byte_arr.getvalue(), detail=0))
        logger.info(f"  [2/4] OCR fini en {time.time()-t1:.2f}s (Texte: {len(raw_text[1000:])} chars)")
        
        # Nettoyage RAM
        del pdf_content, images, img_byte_arr
        gc.collect()

        t2 = time.time()
        metadata = extract_metadata_local(raw_text)
        if not metadata:
            logger.warning(f"  [!] Saut de fichier : Échec extraction métadonnées.")
            continue
        logger.info(f"  [3/4] Extraction par LLM (Ollama) finie en {time.time()-t2:.2f}s")

        t3 = time.time()
        level = str(metadata.get('education_level') or "Inconnu").replace(" ", "")
        serie = str(metadata.get('serie') or "").replace(" ", "")
        year = str(metadata.get('year') or "0000")
        disc = str(metadata.get('discipline') or "Matiere").replace(" ", "_")
        lang = str(metadata.get('language') or "FR").replace(" ", "")
        school = str(metadata.get('school_name') or "Anonyme").replace(" ", "_")

        new_key = f"processed/{level}_{serie}/{year}_{disc}_{school}.pdf"
        
        # Transfert R2
        s3.copy_object(
            Bucket=R2_CONFIG["bucket_name"],
            CopySource={'Bucket': R2_CONFIG["bucket_name"], 'Key': file_key},
            Key=new_key
        )
        s3.delete_object(Bucket=R2_CONFIG["bucket_name"], Key=file_key)
        
        total_proc = time.time() - start_total
        logger.info(f"  [4/4] Rangement R2 fini. Chemin : {new_key}")
        
        cursor.execute(
            "INSERT INTO extractions (original_path, extracted_text, json_output, new_r2_path, proc_time_sec) VALUES (?, ?, ?, ?, ?)",
            (file_key, raw_text, json.dumps(metadata, ensure_ascii=False), new_key, total_proc)
        )
        conn.commit()
        
        logger.info(f"✅ Terminé avec succès en {total_proc:.2f}s")

      except Exception as e:
        logger.error(f"❌ Erreur critique sur {file_key}: {e}")
        continue

if __name__ == "__main__":
    logger.info("Démarrage du pipeline d'archivage...")
    try:
        process_exam_files()
    finally:
        conn.close()
        logger.info("Base de données fermée. Fin du script.")