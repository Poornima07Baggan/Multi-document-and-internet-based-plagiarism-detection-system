from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# 🤖 LOAD THE ML MODEL (Loads once when server starts to keep the app fast)
# 'all-MiniLM-L6-v2' is a lightweight, super-fast model perfect for catching paraphrasing!
print("Loading Machine Learning Paraphrasing Model... (This may take a few seconds)")
semantic_model = SentenceTransformer('all-MiniLM-L6-v2')

def calculate_similarity(documents):
    """
    Takes a list of document texts, converts them to semantic vectors, 
    and returns a matrix of their similarity scores.
    """
    if not documents:
        return []
        
    # 1. Convert all text into mathematical meaning (Embeddings)
    embeddings = semantic_model.encode(documents)
    
    # 2. Calculate how close the meanings are to each other (Cosine Similarity)
    similarity_matrix = cosine_similarity(embeddings)
    
    return similarity_matrix