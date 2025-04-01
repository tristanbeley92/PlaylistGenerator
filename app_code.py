from flask import Flask, redirect, request, session, render_template
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

    return redirect('/recommendations') # Redirect to recommendations page after login

@app.route('/recommendations') #Song recommendations page
def get_recommendations():
    # This is where you would use the access token to get recommendations
    # You can use the access token to make requests to Spotify's API

    genre = request.args.get("genre", "house") # Default to 'pop' if no genre is provided
    access_token = session.get('access_token')

    if not access_token:
        return redirect('/login') # If no access token, redirect to login

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

    response = requests.get(url, headers=headers, params=params)

    
    if response.status_code != 200:
        return f"Error fetching recommendations, status code: {response.status_code}"


    search_response = response.json()

    tracks = search_response.get("tracks", []).get("items", [])

    if not tracks:
        return "No tracks found for this genre"

    simplified_tracks = []
    for track in tracks:
        simplified_tracks.append({
            "name" : track["name"],
            "artist" : track["artists"][0]["name"],
            "uri" : track["uri"],
            "image" : track["album"]["images"][0]["url"] if track["album"]["images"] else None
        })    

    session['recommended_tracks'] = simplified_tracks  # Store the recommended tracks in the session

    return render_template('recommendations.html', tracks=simplified_tracks, genre=genre)  # Render the recommendations page with the results

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

        session['playlist_id'] = playlist_data.get("id")# Store the last created playlist ID in the session\
        return f'Succesfully created playlist! <a href="{playlist_url}" target="_blank"> Open In Spotify</a>'
    
@app.route('/create_playlist_form')  #Page to create a playlist
def create_playlist_form():
    return render_template('create_playlist_form.html')  # Render the HTML form for creating a playlist

@app.route('/add_tracks', methods=['POST']) #Add tracks to the playlist
def add_tracks():
    access_token = session.get('access_token')
    playlist_id = session.get('playlist_id')

    if not access_token:
        return redirect('/login')
    if not playlist_id:
        return "No playlist ID found in session, Create one first."
    
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
        print("Tracks added successfully")
        return redirect('/recommendations')
    else:
        return f"Failed to add tracks: {response.status_code} - {response.text}"

if __name__ == '__main__': #
    app.run(port=8888)
