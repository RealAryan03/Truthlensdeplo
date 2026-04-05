from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import os

# Load DistilBERT model and tokenizer
model_path = os.path.join(os.path.dirname(__file__), ".")
tokenizer = AutoTokenizer.from_pretrained(model_path)
model = AutoModelForSequenceClassification.from_pretrained(model_path)

def get_bert_score(text):
    """
    Uses DistilBERT model to predict the authenticity score of the text.
    Returns a score between 0 and 1, where higher values indicate more authentic content.

    Args:
        text (str): The input text to analyze

    Returns:
        float: Probability score between 0 and 1
    """
    # Tokenize the input text
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512, padding=True)

    # Run inference
    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits

    # Apply softmax to get probabilities
    probabilities = torch.softmax(logits, dim=1)

    # Return the probability of being authentic (class 1)
    # Assuming class 1 represents authentic/real content
    return probabilities[0][1].item()