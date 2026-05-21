import pyaudio
p = pyaudio.PyAudio()
info = p.get_device_info_by_index(24)
print(f'Device: {info["name"]}')
print(f'Default sample rate: {info["defaultSampleRate"]}')
for rate in [8000, 16000, 22050, 44100, 48000]:
    try:
        supported = p.is_format_supported(rate, input_device=24, input_channels=1, input_format=pyaudio.paInt16)
        print(f'  {rate}Hz: supported')
    except:
        print(f'  {rate}Hz: NOT supported')
p.terminate()
