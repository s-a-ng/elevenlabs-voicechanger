from pygame import mixer 
from pydub import AudioSegment
from termcolor import colored
from threading import Thread

import io, os, re
import time, wave, json

import pyaudio

import requests

import webrtcvad, requests


def clear():
    os.system('cls' if os.name == 'nt' else 'clear')

clear()
time.sleep(1)

voices_map = {

}

def threaded_function(func):
    def wrapper(*args, **kwargs):
        t = Thread(target=func, args=args, kwargs=kwargs)
        t.daemon = True
        t.start()
        return t
    return wrapper



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

while True:
    chunk_transcription_enabled = input("Transcribe audio chunks? (This will help properly detect speech, at the cost of time)").lower().strip()
    if chunk_transcription_enabled in ("y", "n"):
        chunk_transcription_enabled = chunk_transcription_enabled == "y"
        break

clear()
mixer.init() 
mixer.quit() 
mixer.init(devicename='CABLE Input (VB-Audio Virtual Cable)') 

RATE = 16000
CHANNELS = 1
CHUNK = 480
RECORD_SECONDS = 3

ELEVENLABS_STABILITY = 0.4
ELEVENLABS_SIMILARITY_BOOST = 0.5

def convert_wav_buffer_to_flac(wav_buffer):
    sound = AudioSegment.from_wav(wav_buffer)

    sound = sound.set_sample_width(2)

    flac_buffer = io.BytesIO()
    sound.export(flac_buffer, format="flac")
    raw_flac_bytes = flac_buffer.getvalue()

    return raw_flac_bytes

voice_chunks = {}
chunk_index = 0

class AudioChunk:
    def __init__(self, wav_buffer):
        global chunk_index
        self.wav_buffer = wav_buffer
        self.flac_data = convert_wav_buffer_to_flac(wav_buffer)

        self.eleven_labs_data = None

        self.chunk_complete_processing = False

        self.transcription = ""
        self.index = chunk_index
        voice_chunks[chunk_index] = self
        chunk_index += 1 
    
    def remove_chunk(self):
        del voice_chunks[self.index]

    @threaded_function
    def begin_processing(self):
        if chunk_transcription_enabled:
            self.transcribe_then_sts()
        else:
            print("calling 11labs")
            self.apply_speech_to_speech()


    def transcribe_then_sts(self): 
        url = f"http://www.google.com/speech-api/v2/recognize?client=chromium&lang=en-US&key=AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"
        headers = {"Content-Type": "audio/x-flac; rate=" + str(RATE)}
        response = requests.post(url, data=self.flac_data, headers=headers)

        try: 
            response_json = json.loads(response.text.split('\n', 1)[1])
            transcript = response_json["result"][0]["alternative"][0]["transcript"]

            self.transcription = transcript

            self.apply_speech_to_speech()

           # print("sucessfully transcribed speech, calling sts")
        except Exception as e:
            self.remove_chunk()
    
    def apply_speech_to_speech(self):
        try: 
            url = f"https://api.elevenlabs.io/v1/speech-to-speech/{voice_id}/stream"
            headers = {
                "Authorization" : Bearer
            }
            data = {
                "model_id": "eleven_english_sts_v2",
                "voice_settings" : json.dumps({
                    "stability": ELEVENLABS_STABILITY,    
                    "similarity_boost": ELEVENLABS_SIMILARITY_BOOST,  
                }),
            }

            self.wav_buffer.seek(0) 
            files = {'audio': ('audio.wav', self.wav_buffer, 'audio/wav')}

            response = requests.post(url, headers=headers, data=data, files=files)
            print("repsonse")
            content = response.content
            if len(content) <= 200: 
                print(content)
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
                    self.remove_chunk()
                    return 
                except Exception:
                    self.remove_chunk()
                    return 
                
            self.eleven_labs_data = io.BytesIO(content) 
            self.chunk_complete_processing = True 

        except Exception:
            self.remove_chunk()
            return 



vad = webrtcvad.Vad() 
vad.set_mode(3) # most aggressive (1-3)

audio = pyaudio.PyAudio()
stream = audio.open(format=pyaudio.paInt16,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    frames_per_buffer=CHUNK)


@threaded_function
def record_audio():
    while True:
        frames = []
        num_silent_chunks = 0
        noise_chunks = 0

        one_second = RATE // CHUNK
        frame_cap = one_second * RECORD_SECONDS
        
        while True:
            data = stream.read(CHUNK)
            is_speech_chunk = vad.is_speech(data, RATE)

            if is_speech_chunk:
                num_silent_chunks = 0
                noise_chunks += 1 
            else:
                num_silent_chunks += 1

            frames.append(data)
            if len(frames) >= frame_cap and num_silent_chunks >= one_second:
                speech_percent = noise_chunks / len(frames) * 100
                threshold = 20 / (RECORD_SECONDS / 3) 

                print(colored(f"{int(speech_percent)}% of chunk detected as speech (threshold is {threshold})", "light_blue"))
                if speech_percent < threshold:
                    break

                print(colored("threshold reached", "blue"))
                wav_buffer = io.BytesIO()
                with wave.open(wav_buffer, 'wb') as wf:
                    wf.setnchannels(CHANNELS)
                    wf.setsampwidth(audio.get_sample_size(pyaudio.paInt16))
                    wf.setframerate(RATE)
                    wf.writeframes(b''.join(frames))

                wav_buffer.seek(0) 

                chunk = AudioChunk(wav_buffer)
                chunk.begin_processing()

                break

def play_audio(chunk):
    print(colored("Playing audio chunk", "green"))
    file_path = "temp_audio.mp3"

    with open(file_path, 'wb') as f:
        f.write(chunk.eleven_labs_data.getvalue())


    mixer.music.load(file_path)
    mixer.music.set_volume(1.0)
    mixer.music.play()

    while mixer.music.get_busy():
        time.sleep(0.1)

    mixer.music.stop()
    mixer.music.unload()
    os.remove(file_path)
    chunk.remove_chunk()

def play_audio_chunks(): # Race condition galore
    while True:
        if not voice_chunks:  
            continue

        keys = list(voice_chunks.keys())

        if len(keys) == 0:
            continue
        
        min_key = min(keys)
        chunk = voice_chunks.get(min_key)

        if not chunk:
            continue

        try:
            if chunk.chunk_complete_processing:
                break
        except AttributeError: 
            continue

    play_audio(chunk) 

def main():
    try:
        while True:
            play_audio_chunks()
    except KeyboardInterrupt:
        print(colored("Stopping voice changer", "red"))
        stream.stop_stream()
        stream.close()
        audio.terminate()
        exit()

record_audio()
main()
