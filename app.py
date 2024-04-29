from flask import Flask, request, jsonify, g, render_template, session, redirect, url_for
import sqlite3
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime
app = Flask(__name__)
app.secret_key = 'your_secret_key'
DATABASE = 'news_database.db'

# Database connection functions
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.execute("PRAGMA foreign_keys = 1")  # Enable foreign key support
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# Ensure the news table has the last_accessed column
def init_db():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS news (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT,
                    headline TEXT,
                    authors TEXT,
                    link TEXT,
                    short_description TEXT,
                    date TEXT,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    db.commit()

# Initialize database when the app starts
with app.app_context():
    init_db()

# TF-IDF and recommendation logic
def calculate_cosine_similarity(query, tfidf_matrix, tfidf_vectorizer):
    # Calculate TF-IDF vector for the query
    query_vector = tfidf_vectorizer.transform([query])

    # Calculate cosine similarity between query vector and all news articles
    cosine_similarities = cosine_similarity(query_vector, tfidf_matrix)

    # Get indices of articles sorted by similarity (descending order)
    sim_indices = cosine_similarities.argsort()[0][::-1]

    return sim_indices

def recommend_similar_news(news_id, num_recommendations=5):
    db = get_db()
    cursor = db.cursor()

    # Fetch headlines, descriptions, and links from the news table
    cursor.execute('''SELECT id, headline, short_description, image_url FROM news WHERE id != ?''', (news_id,))
    rows = cursor.fetchall()
    articles_data = [{'id': row[0], 'headline': row[1], 'short_description': row[2], 'image_url': row[3]} for row in rows]

    # Initialize TF-IDF Vectorizer
    tfidf_vectorizer = TfidfVectorizer(stop_words='english')
    headlines_descriptions = [f"{row['headline']} {row['short_description']}" for row in articles_data]
    tfidf_matrix = tfidf_vectorizer.fit_transform(headlines_descriptions)

    # Calculate cosine similarity
    cursor.execute('''SELECT headline, short_description FROM news WHERE id = ?''', (news_id,))
    query_article = cursor.fetchone()
    if query_article:
        query = f"{query_article[0]} {query_article[1]}"
        sim_indices = calculate_cosine_similarity(query, tfidf_matrix, tfidf_vectorizer)

        # Recommend similar news articles with links (unique recommendations)
        recommended_articles = []
        seen_articles = set()  # Keep track of seen articles to avoid duplicates
        for idx in sim_indices:
            article = articles_data[idx]
            if article['id'] != news_id and article['id'] not in seen_articles:
                recommended_articles.append(article)
                seen_articles.add(article['id'])
                if len(recommended_articles) == num_recommendations:
                    break

        return recommended_articles
    else:
        return []


# Routes
@app.route('/')
def index():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''SELECT id, headline, category FROM news ORDER BY last_accessed DESC''')
    news_list = [{'id': row[0], 'headline': row[1], 'category': row[2]} for row in cursor.fetchall()]
    categories = set([row['category'] for row in news_list])
    return render_template('index.html', news_list=news_list, categories=categories)

@app.route('/category/<string:category_name>')
def category_news(category_name):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''SELECT id, headline, category FROM news WHERE category = ?''', (category_name,))
    category_news_list = [{'id': row[0], 'headline': row[1], 'category': row[2]} for row in cursor.fetchall()]
    categories = set([row['category'] for row in category_news_list])
    return render_template('category_news.html', category_name=category_name, news_list=category_news_list, categories=categories)


@app.route('/filter_news', methods=['POST'])
def filter_news():
    if request.method == 'POST':
        category = request.form.get('category')
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''SELECT id, headline, category FROM news WHERE category = ?''', (category,))
        filtered_news = [{'id': row[0], 'headline': row[1], 'category': row[2]} for row in cursor.fetchall()]
        return render_template('filtered_news.html', category=category, filtered_news=filtered_news)
    else:
        return jsonify({'error': 'Method not allowed'}), 405
@app.route('/news/<int:news_id>')
def news_details(news_id):
    db = get_db()
    cursor = db.cursor()
    
    # Fetch news details based on the news ID, including the link
    cursor.execute('''SELECT id, headline, short_description, link , image_url FROM news WHERE id = ?''', (news_id,))
    news_data = cursor.fetchone()
    
    if news_data:
        # Fetch recommendations based on the news ID
        #print("Debug: Link value received in news_details route:", news_data[3])  # Access link using index
 # Debug statement
        recommendations = recommend_similar_news(news_id)
        # Pass the 'id' along with other properties to the template
        return render_template('news_details.html', news=news_data, news_link=news_data[3],news_img=news_data[4], recommendations=recommendations)
    else:
        return jsonify({'error': 'News not found'}), 404
    
@app.route('/read_more/<int:news_id>')
def read_more(news_id):
    db = get_db()
    cursor = db.cursor()

    # Update the last_accessed timestamp for the news article
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("UPDATE news SET last_accessed = ? WHERE id = ?", (current_time, news_id))
    db.commit()
    print(f"News item {news_id} accessed at {current_time}")  # Debug statement

    # Redirect to the news details page
    return redirect(url_for('news_details', news_id=news_id))

@app.route('/news/<int:news_id>/link')
def get_news_link(news_id):
    db = get_db()
    cursor = db.cursor()

    # Fetch the news link based on news ID
    cursor.execute('''SELECT link FROM news WHERE id = ?''', (news_id,))
    news_link = cursor.fetchone()

    if news_link:
        return jsonify({'link': news_link[0]})
    else:
        return jsonify({'error': 'News link not found'}), 404

if __name__ == '__main__':
    app.run(debug=True)
