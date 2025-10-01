from flask import Flask, redirect, request, session, render_template, url_for
import requests
import os
from dotenv import load_dotenv
import base64
import random

load_dotenv()
app = Flask(__name__)
app.secret_key = os.urandom(24)  # Set a secret key for session management

CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
REDIRECT_URI = os.getenv('SPOTIFY_REDIRECT_URI')

AUTH_URL = 'https://accounts.spotify.com/authorize'#Spotifys URL for authentication
TOKEN_URL = 'https://accounts.spotify.com/api/token'
SCOPE = 'playlist-modify-public playlist-modify-private'# scope = permissions from user

@app.route('/', endpoint='welcome') #Home page
def welcome():
    return render_template('welcome.html')  # Render the welcome page template

@app.route('/home', endpoint='home') #Home page
def home():
    access_token = session.get("access_token")

    # If no token, force them to login first
    if not access_token:
        return redirect("/login")
    return render_template('home.html')  # Render the home page template

@app.route('/start', methods=['GET', 'POST']) #Start page
def start():
    access_token = session.get('access_token')
    if not access_token:
        return redirect('/login')  # Redirect to login if no access token
    
    if request.method == 'POST':
        session['genre'] = request.form.get("genre", "house")
        _clear_queue()
        return redirect(url_for('start', genre=session['genre']))
    
    genre = request.args.get('genre', session.get('genre', 'house'))

    q = session.get('track_queue') or []
    idx = session.get('current_track_index', 0)
    if q and idx < len(q):
        track, i, total = _current_track()
        if not track:
            _clear_queue()
            return redirect(url_for('start', genre=genre))
        return render_template('recommend-card.html',
                               track=track, index=i, total=total, genre=genre)
    
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "q": f"genre:{genre}",
        "type": "track",
        "limit": 10,
        "offset": random.randint(0,400),
        "market": "CA"
    }

    r = requests.get("https://api.spotify.com/v1/search", headers=headers, params=params)
    if not r.ok:
        return f"Error fetching recommendations, status code: {r.status_code}", 400
    
    items = r.json().get("tracks", {}).get("items", [])
    if not items:
        return "No tracks found for this genre", 200
    
    tracks = [{
        "name": t["name"],
        "artist": t["artists"][0]["name"],
        "uri": t["uri"],
        "image": t["album"]["images"][0]["url"] if t["album"]["images"] else None
    } for t in items]
    
    _init_queue(tracks)
    track, i, total = _current_track()
    return render_template('recommend-card.html',
                           track=track, index=i, total=total, genre=genre)

@app.route('/login') #Login page
def login():
    auth_query = { "response_type": "code", 
                  "redirect_uri" : REDIRECT_URI,
                  "scope" : SCOPE,
                  "client_id" : CLIENT_ID,
                  "show_dialog": "true"
                  }
    
    url_args = "&".join([f"{key}={requests.utils.quote(val)}" for key, val in auth_query.items()])
    auth_url = f"{AUTH_URL}?{url_args}"
    return redirect(auth_url)

@app.route('/callback') #Callback page, authorization code is sent here
def callback():
    # Spotify redirects back to this endpoint with a code
    code = request.args.get("code")


    auth_str = f"{CLIENT_ID}:{CLIENT_SECRET}"
    b64_auth_str = base64.b64encode(auth_str.encode()).decode()

  
    headers = {
        "Authorization": f"Basic {b64_auth_str}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "authorization_code",
        "code": code,                   # The code we got from Spotify
        "redirect_uri": REDIRECT_URI    
    }

    # Send POST request to Spotify to get the access token
    response = requests.post(TOKEN_URL, headers=headers, data=data)
    token_info = response.json()

    # Pull out tokens from the response
    access_token = token_info.get("access_token")
    refresh_token = token_info.get("refresh_token")

    session['access_token'] = access_token
    session['refresh_token'] = refresh_token

    return redirect(url_for('home')) # Redirect to recommendations page after login

@app.route('/create_playlist', methods=['POST']) #Create a playlist code and logic
def create_playlist():
    access_token = session.get('access_token')
    if not access_token:
        return redirect('/login')  # Redirect to login if no access token

    playlist_name = request.form.get("playlist_name", "New Playlist")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    # Get the user's Spotify ID
    response = requests.get("https://api.spotify.com/v1/me", headers=headers)
    user_id = response.json().get("id")

    # Create a new playlist
    url = f"https://api.spotify.com/v1/users/{user_id}/playlists"
    create_playlist = requests.post(
        url,
        headers=headers,
        json={
            "name": playlist_name,
            "description": "Created using Flask and Spotify API",
            "public": False  # Set to True or False based on your preference
        }
    )


    if create_playlist.status_code == 201: #If playlist is created successfully, sends user to the playqlist via url
        playlist_data = create_playlist.json()
        playlist_url = playlist_data.get("external_urls", {}).get("spotify", "#")

        session['playlist_id'] = playlist_data.get("id")# Store the last created playlist ID in the session
        session['playlist_url'] = playlist_url

        return redirect(url_for('home'))

@app.route('/decision', methods=['POST'])  # Handle user decisions
def decision():
    access_token = session.get('access_token')
    if not access_token:
        return redirect('/login')

    action = request.form.get('action')  # 'add' or 'skip'
    uri    = request.form.get('uri')
    genre  = request.form.get('genre', session.get('genre', 'house'))

    track, idx, total = _current_track()
    if not track:
        return redirect(url_for('start', genre=genre))

    if action == 'add':
        # Add to playlist if one exists
        playlist_id = session.get('playlist_id')
        if playlist_id and uri:
            headers = {"Authorization": f"Bearer {access_token}",
                       "Content-Type": "application/json"}
            requests.post(
                f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
                headers=headers, json={"uris": [uri]}
            )
        session['likes'] = session.get('likes', []) + [track]
    else:
        session['dislikes'] = session.get('dislikes', []) + [track]

    _advance()
    nxt, i2, total2 = _current_track()
    if not nxt:
        # End of queue — show “That’s all for now”
        return render_template('recommend-card.html',
                               track=None, index=i2, total=total2,
                               genre=genre, gpt_summary=session.get('gpt_summary'))

    return redirect(url_for('start', genre=genre))

# --- helpers ----
def _init_queue(tracks):
    session['track_queue'] = tracks
    session['current_track_index'] = 0
    session.setdefault('likes', [])
    session.setdefault('dislikes', [])

def _current_track():
    q = session.get('track_queue', [])
    i = session.get('current_track_index', 0)
    if 0 <= i < len(q):
        return q[i], i, len(q)   # exactly three
    # when the queue is empty or we're past the end:
    return None, i, len(q)       # exactly three

def _clear_queue():
    session.pop('track_queue', None)
    session.pop('current_track_index', None)


def _advance():
    session['current_track_index'] = session.get('current_track_index', 0) + 1

if __name__ == '__main__': #
    app.run(port=8888)
