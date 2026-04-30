from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def calculate_similarity(text1, text2):
    try:
        if not text1.strip() or not text2.strip():
            return 0.0
        
        vectorizer = TfidfVectorizer()
        tfidf = vectorizer.fit_transform([text1, text2])
        sim = cosine_similarity(tfidf[0:1], tfidf[1:2])
        return round(float(sim[0][0]) * 100, 2)
    except Exception as e:
        print(f"Error: {e}")
        return 0.0
