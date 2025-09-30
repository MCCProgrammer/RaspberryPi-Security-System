import subprocess
import time
import os
import threading

# Use the script's directory as the project root
project_dir = os.path.dirname(os.path.abspath(__file__))
recordings_dir = os.path.join(project_dir, "recordings")

# Ensure the recordings directory exists
os.makedirs(recordings_dir, exist_ok=True)

def run_with_output(command, cwd, name):
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    def reader():
        for line in process.stdout:
            print(f"[{name}] {line}", end="")

    threading.Thread(target=reader, daemon=True).start()
    return process

if __name__ == "__main__":
    # Run video_server.py inside recordings_dir
    flask_proc = run_with_output(["python3", "video_server.py"], recordings_dir, "Flask")
    time.sleep(2)  # Give Flask time to start

    # Run securitySystemDiscord.py inside project_dir
    motion_proc = run_with_output(["python3", "securitySystemDiscord.py"], project_dir, "Motion")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("🛑 Shutting down...")
        flask_proc.terminate()
        motion_proc.terminate()
        flask_proc.wait()
        motion_proc.wait()
        print("✅ Both scripts have been terminated.")