from flask import Flask, render_template, request, redirect, url_for, session, jsonify, g
import sqlite3
import re
import bcrypt
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'
USER_DATABASE = 'login.db'
NEWS_DATABASE = 'news_database.db'

def get_db(db_name):
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(db_name)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = 1")
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def create_table():
    with app.app_context():
        db = get_db(USER_DATABASE)
        db.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                first_login BOOLEAN NOT NULL DEFAULT 1
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS user_interests (
                user_id INTEGER PRIMARY KEY,
                interests TEXT,
                FOREIGN KEY (user_id) REFERENCES accounts (id)
            )
        ''')
        db.commit()


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
    db = get_db(NEWS_DATABASE)
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

@app.route('/login', methods=['GET', 'POST'])
def login():
    msg = ''
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form:
        username = request.form['username']
        password = request.form['password']
        con = get_db(USER_DATABASE)
        cur = con.cursor()
        cur.execute('SELECT * FROM accounts WHERE username = ?', (username,))
        account = cur.fetchone()
        if account is None:
            msg = 'Incorrect username / password!'
        elif account and bcrypt.checkpw(password.encode('utf-8'), account['password']):
            session['loggedin'] = True
            session['id'] = account['id']
            session['username'] = account['username']
            # Check if user has selected interests previously
            if account['first_login'] == 1:
                return redirect(url_for('select_category'))
            else:
                # Retrieve user interests from user_interests table
                cur.execute('SELECT interests FROM user_interests WHERE user_id = ?', (session['id'],))
                interests = cur.fetchone()
                if interests:
                    session['interests'] = interests[0].split(',')
                return redirect(url_for('index'))
        else:
            msg = 'Incorrect username / password!'
    return render_template('login.html', msg=msg)

@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('username', None)
    session.pop('interests', None)
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    msg = ''
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form:
        username = request.form['username']
        password = request.form['password']
        interests = request.form.getlist('interests')  # Get user interests from the form
        con = get_db(USER_DATABASE)
        cur = con.cursor()
        cur.execute('SELECT * FROM accounts WHERE username = ?', (username,))
        account = cur.fetchone()
        if account:
            msg = 'Account already exists!'
        elif not re.match(r'[A-Za-z0-9]+', username):
            msg = 'Username must contain only characters and numbers!'
        elif not username or not password:
            msg = 'Please fill out the form!'
        else:
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            cur.execute('INSERT INTO accounts (username, password) VALUES (?, ?)', (username, hashed_password))
            con.commit()
            # Get the user id of the newly inserted account
            cur.execute('SELECT id FROM accounts WHERE username = ?', (username,))
            user_id = cur.fetchone()[0]
            # Insert user interests into the user_interests table
            cur.execute('INSERT INTO user_interests (user_id, interests) VALUES (?, ?)', (user_id, ','.join(interests)))
            con.commit()
            msg = 'You have successfully registered!'
    elif request.method == 'POST':
        msg = 'Please fill out the form!'
    return render_template('register.html', msg=msg)

@app.route('/select_category', methods=['GET', 'POST'])
def select_category():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        categories = request.form.getlist('category')
        print("Selected categories:", categories)

        if categories:
            session['interests'] = categories
        
        con = get_db(USER_DATABASE)
        cur = con.cursor()
        cur.execute('UPDATE accounts SET first_login = 0 WHERE id = ?', (session['id'],))
        con.commit()

        # Insert or update user interests in the user_interests table
        cur.execute('SELECT * FROM user_interests WHERE user_id = ?', (session['id'],))
        if cur.fetchone():
            cur.execute('UPDATE user_interests SET interests = ? WHERE user_id = ?', (','.join(categories), session['id']))
        else:
            cur.execute('INSERT INTO user_interests (user_id, interests) VALUES (?, ?)', (session['id'], ','.join(categories)))
        con.commit()

        return redirect(url_for('index'))

    return render_template('select_category.html')

@app.route('/index')
def index():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    interests = session.get('interests', [])
    print("User interests:", interests)

    db = get_db(NEWS_DATABASE)
    cursor = db.cursor()

    # Fetch the latest news of the user's interests
    news_list = []
    for interest in interests:
        cursor.execute('''SELECT id, headline, category FROM news WHERE category = ? ORDER BY id DESC''', (interest,))
        news_list.extend([{'id': row[0], 'headline': row[1], 'category': row[2]} for row in cursor.fetchall()])

    # Fetch other news not in the user's interests
    cursor.execute('''SELECT id, headline, category FROM news WHERE category NOT IN ({}) ORDER BY id DESC'''.format(','.join(['?'] * len(interests))), interests)
    other_news = [{'id': row[0], 'headline': row[1], 'category': row[2]} for row in cursor.fetchall()]

    # Combine the news lists, ensuring the user's interests are displayed first
    sorted_news_list = news_list + other_news

    categories = set([row['category'] for row in sorted_news_list])
    
    return render_template('index.html', news_list=sorted_news_list, categories=categories, interests=interests)



@app.route('/category/<string:category_name>')
def category_news(category_name):
    db = get_db(NEWS_DATABASE)
    cursor = db.cursor()
    cursor.execute('''SELECT id, headline, category FROM news WHERE category = ?''', (category_name,))
    category_news_list = [{'id': row[0], 'headline': row[1], 'category': row[2]} for row in cursor.fetchall()]
    categories = set([row['category'] for row in category_news_list])
    return render_template('category_news.html', category_name=category_name, news_list=category_news_list, categories=categories)

@app.route('/filter_news', methods=['POST'])
def filter_news():
    if request.method == 'POST':
        category = request.form.get('category')
        db = get_db(NEWS_DATABASE)
        cursor = db.cursor()
        cursor.execute('''SELECT id, headline, category FROM news WHERE category = ?''', (category,))
        filtered_news = [{'id': row[0], 'headline': row[1], 'category': row[2]} for row in cursor.fetchall()]
        return render_template('filtered_news.html', category=category, filtered_news=filtered_news)
    else:
        return jsonify({'error': 'Method not allowed'}), 405

@app.route('/news/<int:news_id>')
def news_details(news_id):
    db = get_db(NEWS_DATABASE)
    cursor = db.cursor()
    cursor.execute('''SELECT id, headline, short_description, link, image_url FROM news WHERE id = ?''', (news_id,))
    news_data = cursor.fetchone()
    if news_data:
        recommendations = recommend_similar_news(news_id)
        return render_template('news_details.html', news=news_data, news_link=news_data[3], news_img=news_data[4], recommendations=recommendations)
    else:
        return jsonify({'error': 'News not found'}), 404

@app.route('/read_more/<int:news_id>')
def read_more(news_id):
    db = get_db(NEWS_DATABASE)
    cursor = db.cursor()
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("UPDATE news SET last_accessed = ? WHERE id = ?", (current_time, news_id))
    db.commit()
    print(f"News item {news_id} accessed at {current_time}")
    return redirect(url_for('news_details', news_id=news_id))

@app.route('/news/<int:news_id>/link')
def get_news_link(news_id):
    db = get_db(NEWS_DATABASE)
    cursor = db.cursor()
    cursor.execute('''SELECT link FROM news WHERE id = ?''', (news_id,))
    news_link = cursor.fetchone()
    if news_link:
        return jsonify({'link': news_link[0]})
    else:
        return jsonify({'error': 'News link not found'}), 404

if __name__ == '__main__':
    create_table()
    app.run(debug=True, port=8080)
