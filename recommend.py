import sqlite3
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Connect to SQLite database
conn = sqlite3.connect('news_database.db')
c = conn.cursor()

def calculate_cosine_similarity(query, tfidf_matrix, tfidf_vectorizer):
    # Calculate TF-IDF vector for the query
    query_vector = tfidf_vectorizer.transform([query])

    # Calculate cosine similarity between query vector and all news articles
    cosine_similarities = cosine_similarity(query_vector, tfidf_matrix)

    # Get indices of articles sorted by similarity (descending order)
    sim_indices = cosine_similarities.argsort()[0][::-1]

    return sim_indices

def recommend_similar_news(query, num_recommendations=5):
    # Fetch headlines and descriptions from the news table
    c.execute('''SELECT headline, short_description FROM news''')
    rows = c.fetchall()
    headlines_descriptions = [f"{row[0]} {row[1]}" for row in rows]

    # Initialize TF-IDF Vectorizer
    tfidf_vectorizer = TfidfVectorizer(stop_words='english')
    tfidf_matrix = tfidf_vectorizer.fit_transform(headlines_descriptions)

    # Calculate cosine similarity
    sim_indices = calculate_cosine_similarity(query, tfidf_matrix, tfidf_vectorizer)

    # Recommend similar news articles (unique recommendations)
    recommended_articles = []
    seen_articles = set()  # Keep track of seen articles to avoid duplicates
    for idx in sim_indices:
        article = headlines_descriptions[idx]
        if article not in seen_articles:
            recommended_articles.append(article)
            seen_articles.add(article)
            if len(recommended_articles) == num_recommendations:
                break

    return recommended_articles

# Example usage
query = "8 bad habits that make you age faster, according to experts - Fox News"
recommendations = recommend_similar_news(query)

print("Recommended News Articles:")
for idx, article in enumerate(recommendations, 1):
    print(f"{idx}. {article}")

# Close database connection
conn.close()

