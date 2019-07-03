from synthplayer.soundapi.miniaudio import MiniaudioMixed, MiniaudioSequential

m=MiniaudioMixed()
print(m.query_api_version())
print(m.query_apis())
print(m.query_devices())
did = m.query_devices()[1]["id"]
print(m.query_device_details(did))

print()
s=MiniaudioSequential()
print(s.query_api_version())
print(s.query_apis())
print(s.query_devices())
did = s.query_devices()[1]["id"]
print(s.query_device_details(did))
