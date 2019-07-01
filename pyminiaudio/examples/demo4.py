import os
import miniaudio


def samples_path(filename):
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), 'samples', filename)


if __name__ == "__main__":
    devices = miniaudio.Devices()
    selected_device = devices.get_playbacks()[0]
    print("Playing back through {}".format(selected_device.name))

    stream = miniaudio.stream_file(samples_path("music.mp3"))
    device = miniaudio.PlaybackDevice(device_id=selected_device.id)
    device.start(stream)
    input("Audio file playing in the background. Enter to stop playback: ")