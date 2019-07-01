import miniaudio

if __name__ == "__main__":
    devices = miniaudio.Devices()
    print("Backend: {}".format(devices.backend))
    print("\n")

    out_devices = devices.get_playbacks()
    print("Playback Devices")
    for device in out_devices:
        print("  {}".format(device.name))
        print("    {}".format(device.info()))
        print("\n")

    in_devices = devices.get_captures()
    print("Capture Devices")
    for device in in_devices:
        print("  {}".format(device.name))
        print("    {}".format(device.info()))
        print("\n")
