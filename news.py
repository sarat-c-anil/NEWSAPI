import sqlite3
from newsapi import NewsApiClient
import schedule
import time

# Get your API key from newsapi.com and paste it below
newsapi = NewsApiClient(api_key='df1d9fb727544b3889fb37ba181289a5')

# Connect to SQLite database
conn = sqlite3.connect('news_database.db')
c = conn.cursor()

# Create table if not exists
c.execute('''CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                headline TEXT,
                authors TEXT,
                link TEXT,
                image_url TEXT, 
                short_description TEXT,
                date TEXT
            )''')

def insert_articles(articles, category):
    # Get the highest ID from the existing news table
    c.execute("SELECT MAX(id) FROM news")
    max_id = c.fetchone()[0] or 0  # If there are no rows, default to 0

    for article in articles:
        # Extract relevant data from the article
        headline = article['title']
        authors = ', '.join(author['name'] for author in article.get('authors', []))
        link = article['url']
        image_url = article['urlToImage'] if 'urlToImage' in article else ''  # Get image URL
        short_description = article['description']
        date = article['publishedAt']

        # Check if the article with the same URL already exists in the database
        c.execute("SELECT id FROM news WHERE link = ?", (link,))
        existing_id = c.fetchone()
        if existing_id:
            print(f"Skipping duplicate article: {headline}")
            continue  # Skip inserting duplicate articles

        # Increment the ID for the new article
        max_id += 1

        # Insert data into database with the incremented ID
        c.execute('''INSERT INTO news (id, category, headline, authors, link, image_url, short_description, date)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (max_id, category, headline, authors, link, image_url, short_description, date))

    # Commit changes after inserting all articles
    conn.commit()

    print(f"{len(articles)} articles added for category: {category}")

def fetch_and_store_news(categories, country_code='in'):
    for category in categories:
        top_headlines = newsapi.get_top_headlines(category=category, language='en', country=country_code.lower())
        articles = top_headlines['articles'] if 'articles' in top_headlines else []
        if articles:
            insert_articles(articles, category)
            print(f"{len(articles)} articles added for category: {category}")
        else:
            print(f"No articles found for category: {category}")

    # Commit changes after inserting all articles
    conn.commit()
    print("All articles stored in the database.")

def update_news():
    print("Updating news...")
    categories = ['business', 'entertainment', 'general', 'health', 'science', 'technology', 'sports']
    fetch_and_store_news(categories)

def main():
    # Run the update_news function initially
    update_news()

    # Schedule the update_news function to run every 5 minutes
    schedule.every(2).minutes.do(update_news)

    while True:
        # Check for scheduled tasks
        schedule.run_pending()
        time.sleep(1)  # Sleep briefly to avoid excessive CPU usage

    conn.close()
    print("Database connection closed. Exiting program.")

if __name__ == "__main__":
    main()
