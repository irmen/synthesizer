import os
import miniaudio


def samples_path(filename):
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), 'samples', filename)


if __name__ == "__main__":
    devices = miniaudio.Devices()
    print("Available playback devices:")
    playbacks = devices.get_playbacks()
    for p in enumerate(playbacks):
        print(p[0],"= ", p[1])
    choice = int(input("play on which device? "))

    selected_device = playbacks[choice]
    print("Playing back through {}".format(selected_device.name))

    stream = miniaudio.stream_file(samples_path("music.mp3"))
    device = miniaudio.PlaybackDevice(device_id=selected_device._id)    # TODO: fix ownership of _id? or create copy?
    device.start(stream)
    input("Audio file playing in the background. Enter to stop playback: ")
