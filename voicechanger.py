from threading import Thread
from pygame import mixer 
from termcolor import colored
import speech_recognition as sr
import requests, json
import io
import os
import time

os.system("cls")
time.sleep(1)

voices = {
    "santa": "knrPHWnBmmDHMoiMeP3l",
    "perth" : "q5hBSFo3S9aP68ohDElN",
    "obama": "nI5Xtti3YkwPsIQKwmVX",
    "jayln": "1rC87iFsW2c5Ufr6qDwt"
}


def check_bearer(Bearer):
    headers = {
        "Authorization": Bearer
    }
    response = requests.get("https://api.elevenlabs.io/v1/voices", headers=headers)
    return response.status_code == 200

def ask_for_token():
    Bearer = input(colored("Token: ", "green"))
    if not check_bearer(Bearer):
        print(colored("Invalid token. Try again", "red"))
        return ask_for_token()
    print(colored("Valid token!", "green"))
    return Bearer

if not os.path.exists("Bearer.txt"):
    with open("Bearer.txt", "w") as f:
        print(colored("You are missing your token. Please add it below.", "blue"))
        f.write(ask_for_token())

with open("Bearer.txt", "r") as f:
    Bearer = f.read()

if not check_bearer(Bearer):
    print(colored("Your bearer token is invalid. Enter your new one below.", "red"))
    with open("Bearer.txt", "w") as f:
        Bearer = ask_for_token()
        f.write(Bearer)



voice_id = voices[input(colored("Voice: ", "green"))]

mixer.init() 
mixer.quit() 
mixer.init(devicename='CABLE Input (VB-Audio Virtual Cable)') 

def record_audio():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source)
        print(colored("Listening", "green"))
        while True: 
            audio = recognizer.listen(source)
            try:
                print("You said", recognizer.recognize_google(audio))
                return io.BytesIO(audio.get_wav_data())
            except sr.UnknownValueError:
                continue

def play_audio(audio_file):
    file_path = "temp_audio.mp3"

    with open(file_path, 'wb') as f:
        f.write(audio_file.getvalue())


    mixer.music.load(file_path)
    mixer.music.set_volume(1.0)
    mixer.music.play()

    while mixer.music.get_busy():
        time.sleep(0.1)

    mixer.music.stop()
    mixer.music.unload()
    os.remove(file_path)

def transform_speech_endpoint(audio_file):
    try: 
        url = f"https://api.elevenlabs.io/v1/speech-to-speech/{voice_id}/stream"
        headers = {
            "Authorization" : Bearer
        }
        data = {
            "model_id": "eleven_english_sts_v2",
            "voice_settings" : json.dumps({
                "stability": 0.4,
                "similarity_boost": 0.3
            }),
        }

        audio_file.seek(0) 
        files = {'audio': ('audio.wav', audio_file, 'audio/wav')}

        response = requests.post(url, headers=headers, data=data, files=files)

        content = response.content
        if len(content) <= 200: 
            try:
                load = json.loads(content)
                details = load["detail"]
                error_type = details["status"]
                message = details["message"]

                print(f'''
{colored("ElevenLabs returned an error", "light_red")}:
    {colored(f'Error type: "{error_type}"', "red")}
    {colored(f'More details: "{message}"', "red")}
                ''')

                return None
            except Exception:
                return None

        return io.BytesIO(content)  
    except Exception as e:
        return None

def threaded_function(func):
    def wrapper(*args, **kwargs):
        t = Thread(target=func, args=args, kwargs=kwargs)
        t.start()
        return t
    return wrapper

chunk_index = 0
audio_queue = {}
voicechanger_active = True

@threaded_function
def transform_speech(chunk):
    audio_data = chunk["audio_blob"]
    new_data = transform_speech_endpoint(audio_data)  
    chunk["processed_flag"] = True
    if not new_data:
        chunk["failed"] = True
        return 
    chunk["audio_blob"] = new_data

@threaded_function
def record():
    global chunk_index, audio_queue, voicechanger_active
    
    while voicechanger_active:
        audio = record_audio()
        if audio: 
            audio_queue[chunk_index] = {
                "audio_blob" : audio, 
                "failed" : False, 
                "processed_flag" : False
            }
            transform_speech(audio_queue[chunk_index])
            chunk_index += 1

def main():
    try:
        global audio_queue, voicechanger_active
        while True:
            if not audio_queue:  
                continue
            first_index = min(audio_queue.keys())
            data = audio_queue.pop(first_index)                
            while not data["processed_flag"]:
                continue
                
            if data["failed"]:
                print(colored("Failed to convert this chunk. There may be something wrong with your ElevenLabs account.", "red"))
                continue
            print(colored("Playing processed audio", "green"))
            play_audio(data["audio_blob"]) 

    except KeyboardInterrupt:
        print("Stopping")
        voicechanger_active = False
        exit()

record()
main()
