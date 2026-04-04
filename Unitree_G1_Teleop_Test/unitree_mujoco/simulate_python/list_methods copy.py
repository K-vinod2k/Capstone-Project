from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient
print("Methods of LocoClient:")
for method in dir(LocoClient):
    if not method.startswith("_"):
        print(method)
