import torch
from transformers import DistilBertTokenizer, DistilBertForSequenceClassification
import os
import gdown
import zipfile

BASE_DIR = os.path.dirname(__file__)

MODEL_DIR = os.path.abspath(os.path.join(BASE_DIR, "../bert_model"))

ZIP_PATH = os.path.join(BASE_DIR, "bert_model.zip")

FILE_ID = "1-NgDal2jM3q-9vJWl86AZwZnmNcrdY-H"


def download_model():
    """Download model if not present"""
    if not os.path.exists(MODEL_DIR):
        print("Downloading BERT model...")

        url = f"https://drive.google.com/uc?id={FILE_ID}"
        gdown.download(url, ZIP_PATH, quiet=False)

        print("Extracting model...")

        with zipfile.ZipFile(ZIP_PATH, 'r') as zip_ref:
            zip_ref.extractall(os.path.join(BASE_DIR, ".."))

        print("Model ready!")


download_model()

tokenizer = DistilBertTokenizer.from_pretrained(MODEL_DIR)
model = DistilBertForSequenceClassification.from_pretrained(MODEL_DIR)
model.eval()


def get_bert_score(text):
    """
    Returns probability of REAL news (class 1)
    """

    if isinstance(text, str):
        texts = [text]
    else:
        texts = text

    encodings = tokenizer(
        texts,
        truncation=True,
        padding=True,
        return_tensors="pt"
    )

    with torch.no_grad():
        outputs = model(**encodings)
        probs = torch.softmax(outputs.logits, dim=-1)

    return probs[:, 1].tolist() if len(probs) > 1 else probs[0, 1].item()