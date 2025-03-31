from flask import Flask, redirect, request
import requests
import os
from dotenv import load_dotenv
import base64

load_dotenv()
app = Flask(__name__)

CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
REDIRECT_URI = os.getenv('SPOTIFY_REDIRECT_URI')

AUTH_URL = 'https://accounts.spotify.com/authorize'#Spotifys URL for authentication
TOKEN_URL = 'https://accounts.spotify.com/api/token'

SCOPE = 'playlist-modify-public playlist-modify-private'# scope = permissions from user

#redirect to spotify login page

@app.route('/login')
def login():
    auth_query = { "response_type": "code", "redirect_uri" : REDIRECT_URI,"scope" : SCOPE,"client_id" : CLIENT_ID, "show_dialog": "true" }
    url_args = "&".join([f"{key}={requests.utils.quote(val)}" for key, val in auth_query.items()])
    auth_url = f"{AUTH_URL}?{url_args}"

    return redirect(auth_url)

@app.route('/callback')
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

    # Display the tokens in the browser
    return f"Access Token: {access_token}<br><br>Refresh Token: {refresh_token}"


if __name__ == '__main__':
    app.run(port=8888)