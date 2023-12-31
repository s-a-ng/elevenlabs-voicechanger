from threading import Thread
from pygame import mixer 
from termcolor import colored
import speech_recognition as sr
import requests, json
import io
import os
import time
import re 
os.system("cls")
time.sleep(1)

voices_map = {

}

def remove_emojis(text):
    emoji_pattern = re.compile("["
                               u"\U0001F600-\U0001F64F"  # emoticons
                               u"\U0001F300-\U0001F5FF"  # symbols & pictographs
                               u"\U0001F680-\U0001F6FF"  # transport & map symbols
                               u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
                               u"\U00002500-\U00002BEF"  # chinese char
                               u"\U00002702-\U000027B0"
                               u"\U00002702-\U000027B0"
                               u"\U000024C2-\U0001F251"
                               u"\U0001f926-\U0001f937"
                               u"\U00010000-\U0010ffff"
                               u"\u2640-\u2642"
                               u"\u2600-\u2B55"
                               u"\u200d"
                               u"\u23cf"
                               u"\u23e9"
                               u"\u231a"
                               u"\ufe0f"  # dingbats
                               u"\u3030"
                               "]+", flags=re.UNICODE)
    return emoji_pattern.sub(r'', text)


def get_voices(Bearer):
    headers = {
        "Authorization": Bearer
    }

    parsed_voices = { }
    voices = requests.get("https://api.elevenlabs.io/v1/voices", headers=headers).json()

    voices = voices['voices']
    
    print(colored("Available voices: ", "blue"))

    for voice in voices:
        category = voice["category"]
        name = remove_emojis(voice["name"]).strip()
        voices_map[name] = voice["voice_id"]
        print(colored(f"    - {name} ({category})", "light_blue"))

    return parsed_voices

def check_bearer(Bearer):
    headers = {
        "Authorization": Bearer
    }
    response = requests.get("https://api.elevenlabs.io/v1/voices", headers=headers)
    return response.status_code == 200

def ask_for_token():
    Bearer = input(colored("Token: ", "light_green"))
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

get_voices(Bearer)

while True: 
    voice_input = input(colored("Select your voice: ", "light_green"))
    voice_id = voices_map.get(voice_input)
    if voice_id:
        break
    else:
        print(colored("Invalid voice", "red"))


os.system("cls")

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
            #a = time.time()
            try:
                transcription = recognizer.recognize_google(audio) # detects voice activity better. if it errors it could not pick up any speech
                #print("You said", transcription)
                #print(time.time()-a)
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
    {colored(f'- Error type: "{error_type}"', "red")}
    {colored(f'- More details: "{message}"', "red")}

{colored(f"There is a good chance this error is because your Bearer token expired.{chr(10)}Please try restarting the program", "red")}
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
        t.daemon = True
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
            print(colored("Playing audio chunk", "green"))
            play_audio(data["audio_blob"]) 

    except KeyboardInterrupt:
        print("Stopping")
        voicechanger_active = False
        exit()

record()
main()
