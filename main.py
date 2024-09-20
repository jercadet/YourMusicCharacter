import json
import os
import time
from flask import (
    Flask,
    redirect,
    request,
    session,
    url_for,
    jsonify,
    render_template,
    send_from_directory,
)
from flask_session import Session
from spotipy.oauth2 import SpotifyOAuth
import spotipy
import logging
import sqlite3

# Initialize Flask app and Session
app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Ensure environment variables are set correctly
SPOTIPY_CLIENT_ID = "dca7d8a6114c4c76ba8022ff679fd79a"
SPOTIPY_CLIENT_SECRET = "5b9fdf9f6c2847adbe45d1052edc7ca2"
SPOTIPY_REDIRECT_URI = "http://127.0.0.1:5000/callback"

# Initialize SpotifyOAuth object with credentials and scope
sp_oauth = SpotifyOAuth(
    client_id=SPOTIPY_CLIENT_ID,
    client_secret=SPOTIPY_CLIENT_SECRET,
    redirect_uri=SPOTIPY_REDIRECT_URI,
    scope="user-top-read",
)

# Set up logging
logging.basicConfig(level=logging.DEBUG)


# SQLite database connection
def create_connection():
    conn = sqlite3.connect("characters.db")
    return conn


# Retrieve a character based on genre from the database
def get_character_by_genre(genre):
    character_type = classify_character([genre])
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
    SELECT name, image_url, genre FROM characters WHERE genre = ? ORDER BY RANDOM() LIMIT 1
    """,
        (character_type,),
    )
    character = cursor.fetchone()
    conn.close()
    return character


# Function to set up the database
def setup_database():
    conn = create_connection()
    c = conn.cursor()

    # Drop the table if it exists to start fresh
    c.execute("DROP TABLE IF EXISTS characters")

    # Create the characters table
    c.execute(
        """
    CREATE TABLE characters
    (id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    image_url TEXT NOT NULL,
    genre TEXT NOT NULL)
    """
    )

    # Add new sample data
    sample_data = [
        ("Rock Rebel", "character1.png", "Rocker"),
        ("Pop Princess", "character2.png", "Pop Star"),
        ("Soul Sister", "character3.png", "Soulful Singer"),
        ("Hip Hop Hero", "character4.png", "Hip Hop Artist"),
        ("Folk Troubadour", "character5.png", "Folk Musician"),
    ]
    c.executemany(
        """
    INSERT INTO characters (name, image_url, genre) VALUES (?, ?, ?)
    """,
        sample_data,
    )

    conn.commit()
    conn.close()


# Define character types and their associated genres
genre_file = open("genre_character_mapping.json")
CHARACTER_TYPES = json.load(genre_file)

# calls setup_database at the start of the application
setup_database()

# classifies character based on genres
def classify_character(genres):
    scores = {character: 0 for character in CHARACTER_TYPES}

    for genre in genres:
        if not genre:
            continue
        logging.debug(f"Processing genre: {genre}")
        for character, related_genres in CHARACTER_TYPES.items():
            if any(g in genre.lower() for g in related_genres):
                logging.debug(f"Matched genre '{genre}' with character '{character}'")
                scores[character] += 1

    if all(score == 0 for score in scores.values()):
        logging.debug("No matching genres found. Returning 'Unknown Artist'.")
        return "Unknown Artist"  # Default type if no match is found

    max_character = max(scores, key=scores.get)
    logging.debug(f"Classified character type: {max_character} with score {scores[max_character]}")
    return max_character

# Retrieve the genre for a given artist from Spotify
def get_genre_for_artist(artist_id, sp):
    artist = sp.artist(artist_id)
    print("waaaaa")
    print(artist)
    if 'genres' in artist and len(artist['genres']) > 0:
        return artist['genres'][0]
    return None


# Redirect to Spotify login
@app.route("/login")
def login():
    # Deleting cache file if it exists to have most current data for current user
    cache_path = ".cache"
    if os.path.exists(cache_path):
        os.remove(cache_path)

    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)


# Callback endpoint after Spotify authentication
@app.route("/callback")
def callback():
    session.clear()
    code = request.args.get("code")
    try:
        token_info = sp_oauth.get_access_token(code)
        session["token_info"] = token_info
        return redirect(url_for("top_songs"))
    except spotipy.oauth2.SpotifyOauthError as e:
        logging.error(f"Error in OAuth callback: {str(e)}")
        return jsonify(error=f"Error in OAuth callback: {str(e)}"), 500


# Fetch top songs of the user
@app.route("/top-songs")
def top_songs():
    token_info = get_token()
    if not token_info:
        return redirect("/login")

    sp = spotipy.Spotify(auth=token_info["access_token"])

    try:
        top_songs_data = sp.current_user_top_tracks(limit=5)
        logging.debug(f"Top songs data: {top_songs_data}")
    except spotipy.exceptions.SpotifyException as e:
        logging.error(f"Error fetching top songs: {str(e)}")
        return jsonify(error=f"Error fetching top songs: {str(e)}"), 500

    tracks = []
    for track in top_songs_data["items"]:
        genre = get_genre_for_artist(track["artists"][0]["id"], sp)
        tracks.append(
            {
                "id": track["id"],
                "name": track["name"],
                "artist": track["artists"][0]["name"],
                "genre": genre,
                "preview_url": track["preview_url"],
            }
        )
    # return jsonify(tracks)

    return render_template("top_songs.html", tracks=tracks)


# Fetch character information based on track ID
@app.route("/character/<track_id>")
def character(track_id):
    token_info = get_token()
    if not token_info:
        return redirect("/login")

    sp = spotipy.Spotify(auth=token_info["access_token"])

    try:
        track = sp.track(track_id)
        genre = get_genre_for_artist(track["artists"][0]["id"], sp)
        if not genre:
            genre = "No Genre Found :("
        character = get_character_by_genre(genre)
        if character:
            character_name, character_image_url = character[0], character[1]
        else:
            character_name = "No character found"
            character_image_url = ""
    except spotipy.exceptions.SpotifyException as e:
        logging.error(f"Error fetching character: {str(e)}")
        return render_template('character.html', 
                               track_name="Unknown Track", 
                               character_name="Error", 
                               character_image_url="error.png",
                               character_type="Error",
                               error=f"Error fetching character: {str(e)}")

    return render_template('character.html',
                           track_name=track['name'], 
                           character_name=character_name, 
                           character_image_url=character_image_url,
                           character_type=genre.title())


# Retrieve access token from session, refresh if expired
def get_token():
    token_info = session.get("token_info", None)
    if not token_info:
        return None

    now = int(time.time())
    is_expired = token_info["expires_at"] - now < 60

    if is_expired:
        logging.info("Token expired, refreshing...")
        try:
            token_info = sp_oauth.refresh_access_token(token_info["refresh_token"])
            session["token_info"] = token_info
        except spotipy.oauth2.SpotifyOauthError as e:
            logging.error(f"Error refreshing access token: {str(e)}")
            return None

    return token_info


# Render the homepage
@app.route("/")
def index():
    return render_template("homepage.html")


# Send the css file for the homepage
@app.route("/templates/css/<path:path>")
def index_css(path):
    return send_from_directory("templates/css", path)


# Serve static assets from 'static/assets' directory
@app.route("/assets/<path:path>")
def send_assets(path):
    return send_from_directory("assets", path)


# Handle 404 errors
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html")


# Run the Flask app
if __name__ == "__main__":
    app.run(debug=True)
