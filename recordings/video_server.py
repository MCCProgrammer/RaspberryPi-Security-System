from flask import Flask, request, send_from_directory, render_template_string, redirect
import os
import socket
from dotenv import load_dotenv

# 🔐 Simple password protection (WEB_PASSWORD in the project's .env)
load_dotenv()
WEB_PASSWORD = os.getenv("WEB_PASSWORD")
if not WEB_PASSWORD:
    raise SystemExit("Set WEB_PASSWORD in the .env file before starting the video server.")

app = Flask(__name__)
RECORDINGS_DIR = os.path.abspath(os.path.dirname(__file__))

# 🔒 Authentication
def is_authorized(req):
    return req.args.get("password") == WEB_PASSWORD

@app.route("/")
def home():
    if not is_authorized(request):
        return '<h3>Unauthorized</h3><p>Provide ?password=YOUR_PASSWORD</p>', 401

    # List .mp4 files, newest first
    videos = [
        f for f in os.listdir(RECORDINGS_DIR)
        if f.endswith(".mp4")
    ]
    videos.sort(key=lambda x: os.path.getmtime(os.path.join(RECORDINGS_DIR, x)), reverse=True)

    html = """
    <h2>🎥 Raspberry Pi Video Recordings</h2>
    <ul>
    {% for video in videos %}
        <li>
            <a href="/video?file={{ video }}&password={{ password }}">{{ video }}</a>
        </li>
    {% endfor %}
    </ul>
    """
    return render_template_string(html, videos=videos, password=WEB_PASSWORD)

@app.route("/video")
def get_video():
    if not is_authorized(request):
        return '<h3>Unauthorized</h3><p>Provide ?password=YOUR_PASSWORD</p>', 401

    filename = request.args.get("file")
    if not filename:
        return "Missing 'file' parameter", 400

    if ".." in filename or "/" in filename:
        return "Invalid filename", 400

    file_path = os.path.join(RECORDINGS_DIR, filename)
    if not os.path.isfile(file_path):
        return "File not found", 404

    return send_from_directory(RECORDINGS_DIR, filename)

if __name__ == "__main__":
    # Get local IP
    ip = socket.gethostbyname(socket.gethostname())
    print(f"Server running at http://{ip}:5000/?password={WEB_PASSWORD}")
    app.run(host="0.0.0.0", port=5000)
