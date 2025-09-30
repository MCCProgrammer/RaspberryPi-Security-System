import RPi.GPIO as GPIO
from datetime import datetime
import time
import picamera
import threading
import glob
import os
import requests  # For Discord integration
import socket
import subprocess
from dotenv import load_dotenv
# GPIO Pins
IR = 13
TRIG = 16
ECHO = 18
BUZ = 7
LED = 15

load_dotenv()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
WEB_PASSWORD = os.getenv("WEB_PASSWORD")  # must match the video server
# Globals
state = False
firstTime = True
distanceI = 0
count = 0
lock = threading.Lock()

# Files & Discord
LOG_FILE = "recordings/alarm_log.txt"


# IR Button Codes
Buttons = [
    0x300ff30cf, 0x300ff18e7, 0x300ff7a85, 0x300ff10ef, 0x300ff38c7,
    0x300ff5aa5, 0x300ff42bd, 0x300ff4ab5, 0x300ff52ad, 0x300ffc23d
]
ButtonsNames = [
    "Button1", "Button2", "Button3", "Button4", "Button5",
    "Button6", "Button7", "Button8", "Button9", "ButtonPlay"
]

# Setup GPIO
GPIO.setmode(GPIO.BOARD)
GPIO.setup(IR, GPIO.IN)
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)
GPIO.setup(BUZ, GPIO.OUT)
GPIO.setup(LED, GPIO.OUT)

def get_ip():
    """Get local IP address of the Pi."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def log_event(message):
    """Logs events to a file with timestamp."""
    with open(LOG_FILE, "a") as log_file:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file.write(f"{timestamp} - {message}\n")


def clean_old_videos(max_videos=10):
    """Keeps only the latest max_videos in the recordings folder."""
    video_files = glob.glob("recordings/videoCapture*.h264")
    if len(video_files) > max_videos:
        video_files.sort(key=os.path.getmtime)
        files_to_delete = video_files[:len(video_files) - max_videos]
        for file in files_to_delete:
            try:
                os.remove(file)
                print(f"Deleted old video: {file}")
                log_event(f"Deleted old video: {file}")
            except Exception as e:
                print(f"Error deleting {file}: {e}")
                log_event(f"Error deleting {file}: {e}")

def convert_to_mp4(h264_path):
    """Converts a .h264 video to .mp4 with ffmpeg and returns the .mp4 path."""
    if not os.path.isfile(h264_path):
        print(f"File not found for conversion: {h264_path}")
        return None

    mp4_path = h264_path.replace(".h264", ".mp4")
    # remove stdout/stderr=DEVNULL and "-loglevel" to see ffmpeg logs
    try:
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", "-framerate", "30",
            "-i", h264_path, "-c", "copy", mp4_path
        ], check=True,stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        #print(f"🎥 Converted to MP4: {mp4_path}")
        return mp4_path
    except subprocess.CalledProcessError as e:
        print(f"Error converting to MP4: {e}")
        return None


def send_discord_alert(message, image_path=None, video_path=None):
    """Send a message with optional image or link to Discord."""
    data = {"content": message}
    files = {}

    if image_path and os.path.isfile(image_path):
        files["screenshot"] = (os.path.basename(image_path), open(image_path, "rb"))

    if video_path and os.path.isfile(video_path):
        video_size = os.path.getsize(video_path)
        if video_size < 8 * 1024 * 1024:  # 8 MB limit
            files["video"] = (os.path.basename(video_path), open(video_path, "rb"))
        else:
            ip = get_ip()
            filename = os.path.basename(video_path)
            video_url = f"http://{ip}:5000/video?file={filename}&password={WEB_PASSWORD}"
            message += f"\n🎥 [Video too large — Click to view]({video_url})"

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, data={"content": message}, files=files)
        if response.status_code not in (200, 204):
            print(f"Discord error: {response.status_code} - {response.text}")
        else:
            print("Alert sent to Discord.")
    except Exception as e:
        print(f"Failed to send Discord alert: {e}")



def getBinary():
    num1s = 0
    binary = 1
    command = []
    previousValue = 0
    value = GPIO.input(IR)

    while value:
        time.sleep(0.0001)
        value = GPIO.input(IR)

    startTime = datetime.now()

    while True:
        if previousValue != value:
            now = datetime.now()
            pulseTime = now - startTime
            startTime = now
            command.append((previousValue, pulseTime.microseconds))

        if value:
            num1s += 1
        else:
            num1s = 0

        if num1s > 10000:
            break

        previousValue = value
        value = GPIO.input(IR)

    for (typ, tme) in command:
        if typ == 1:
            if tme > 1000:
                binary = binary * 10 + 1
            else:
                binary *= 10

    if len(str(binary)) > 34:
        binary = int(str(binary)[:34])

    return binary


def convertHex(binaryValue):
    try:
        tmpB2 = int(str(binaryValue), 2)
        return hex(tmpB2)
    except ValueError:
        return "0x0"


def fSensor():
    while True:
        inData = convertHex(getBinary())
        for i, code in enumerate(Buttons):
            if hex(code) == inData:
                print(ButtonsNames[i])
                if ButtonsNames[i] == "ButtonPlay":
                    changeState()
                break


def fSonar():
    global firstTime, distanceI

    while True:
        if not state:
            time.sleep(0.1)
            continue

        GPIO.output(TRIG, False)
        time.sleep(0.1)

        GPIO.output(TRIG, True)
        time.sleep(0.00001)
        GPIO.output(TRIG, False)

        while GPIO.input(ECHO) == 0:
            pulse_start = time.time()

        while GPIO.input(ECHO) == 1:
            pulse_end = time.time()

        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150
        distance = round(distance, 2)

        with lock:
            if firstTime:
                distanceI = distance
                firstTime = False

        print("Distance:", distance, "cm")

        if (distanceI - distance) > 3:
            print("Movement detected! Capturing image and video...")
            GPIO.output(BUZ, True)
            time.sleep(1)
            GPIO.output(BUZ, False)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_file = f"recordings/capture_{timestamp}.jpg"
            video_file = f"recordings/videoCapture_{timestamp}.h264"

            log_event(f"ALARM! Distance changed by {distanceI - distance} cm. Saved {image_file} and {video_file}")

            try:
                with picamera.PiCamera() as camera:
                    camera.resolution = (1280, 720)
                    camera.capture(image_file)
                    camera.start_recording(video_file)
                    time.sleep(10)
                    camera.stop_recording()
                    print(f"Saved {image_file} and {video_file}")
                    
                    mp4_file = convert_to_mp4(video_file)

                # Send to Discord
                alert_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                discord_message = f":rotating_light: **Movement Detected!**\n**Time:** {alert_time}\n**Change:** {distanceI - distance} cm"
                send_discord_alert(discord_message, image_path=image_file, video_path=mp4_file or video_file)
                try:
                    os.remove(video_file)
                    print(f"Deleted old video: {video_file}")
                    log_event(f"Deleted old video: {video_file}")
                except Exception as e:
                    print(f"Error deleting {video_file}: {e}")
                    log_event(f"Error deleting {video_file}: {e}")
                # Clean old videos
                clean_old_videos(max_videos=10)

            except Exception as e:
                print(f"Error capturing image/video: {e}")
                log_event(f"Error capturing image/video: {e}")

        time.sleep(1)


def changeState():
    global state, firstTime
    state = not state
    if state:
        firstTime = True
    GPIO.output(LED, state)
    print("System is", "Active" if state else "Inactive")


def main():
    try:
        GPIO.output(LED, False)
        ir_thread = threading.Thread(target=fSensor, daemon=True)
        sonar_thread = threading.Thread(target=fSonar, daemon=True)
        ir_thread.start()
        sonar_thread.start()

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("Interrupted! Cleaning up GPIO.")
        GPIO.cleanup()


if __name__ == "__main__":
    main()
