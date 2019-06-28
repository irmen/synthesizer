import miniaudio

if __name__ == "__main__":
    in_devices, out_devices = miniaudio.get_devices()
    print("Inputs")
    for device in in_devices:
        print("\t {}".format(device))
    print("Outputs")
    for device in out_devices:
        print("\t {}".format(device))