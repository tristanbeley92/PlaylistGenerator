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

@app.route('/') #Home page
def home():
    access_token = session.get("access_token")

    # If no token, force them to login first
    if not access_token:
        return redirect("/login")
    
    return render_template('home.html')  # Render the home page template

@app.route('/start', methods=['POST']) #Start page
def start():
    genre = request.form.get("genre", "house")
    return redirect(url_for("get_recommendations", genre=genre))

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
    return redirect(auth_url, url_for("home"))

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

@app.route('/recommendations') #Song recommendations page
def get_recommendations():
    # This is where you would use the access token to get recommendations
    # You can use the access token to make requests to Spotify's API

    genre = request.args.get("genre")

    if genre:
        session['genre'] = genre  # Store the selected genre in the session
    else:
        genre = session.get('genre', 'house')  # Default to 'house' if no genre is found

    access_token = session.get('access_token')

    if not access_token:
        return redirect('/login') # If no access token, redirect to login


    #If we already have a queue and were not at the end, show current card 
    q = session.get('track_queue') or []
    idx = session.get('current_track_index', 0)
    print(f"[STATE] queue len={len(q)} idx={idx} genre={genre}")
    if q and idx < len(q):
        track, i, total = _current_track()
        print(f"[RENDER] existing track i={i}/{total}")
        # Safety: if somehow track is None, force a refetch
        if not track:
            _clear_queue()
            return redirect(url_for('get_recommendations', genre=genre))
        return render_template('recommend-card.html',
                               track=track, index=i, total=total, genre=genre)


    #Fetch a fresh batch of recommendations
    url = "https://api.spotify.com/v1/search"  # Spotify's search endpoint for recommendations
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    params = {
        "q": f"genre:{genre}",  # Search query (genre)
        "type": "track",  # Type of item to search for
        "limit": 20,  # Limit the number of results
        "offset": random.randint(0,400),  # Random offset for pagination
        "market": "CA"  # Market to search in (Canada in this case)
    }

    r = requests.get(url, headers=headers, params=params)
    if not r.ok:
        return f"Error fetching recommendations, status code: {r.status_code}"

    items = r.json().get("tracks", {}).get("items", [])
    if not items: return "No tracks found for this genre"

    tracks = [{
        "name": t["name"],
        "artist": t["artists"][0]["name"],
        "uri": t["uri"],
        "image": t["album"]["images"][0]["url"] if t["album"]["images"] else None
    } for t in items]

    _init_queue(tracks)
    track, i, total = _current_track()
    print(f"[RENDER] new track i={i}/{total}")
    return render_template('recommend-card.html',
                           track=track, index=i, total=total, genre=genre)

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

@app.route('/create_playlist_form')  #Page to create a playlist
def create_playlist_form():
    return render_template('create_playlist_form.html')  # Render the HTML form for creating a playlist

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
        return redirect(url_for('get_recommendations', genre=genre))

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

    return redirect(url_for('get_recommendations', genre=genre))

@app.route('/add_tracks', methods=['POST']) #Add tracks to the playlist
def add_tracks():
    access_token = session.get('access_token')
    playlist_id = session.get('playlist_id')

    if not access_token:
        return redirect('/login')
    if not playlist_id:
        return redirect(url_for('home'))
    
    selected_tracks = [v for k, v in request.form.items() if k.startswith('track_')]  # Get selected track URIs from the form

    if not selected_tracks:
        return "No tracks selected to add to the playlist"
    
    url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    response = requests.post(
        url,
        headers=headers,
        json={
            "uris": selected_tracks  # List of track URIs to add to the playlist
        }
    )

    if response.status_code == 201 or response.status_code == 200:
        genre = request.form.get("genre")
        print("Tracks added successfully")
        return redirect(url_for('get_recommendations', genre=genre))
    else:
        return f"Failed to add tracks: {response.status_code} - {response.text}"

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
