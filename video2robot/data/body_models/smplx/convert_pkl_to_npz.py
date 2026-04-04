import pickle
import numpy as np
import sys

# Convert old python 2 latin1 pickle to python 3 npz
with open("SMPLX_NEUTRAL.pkl", "rb") as f:
    data = pickle.load(f, encoding='latin1')

# Cleanup the dict recursively to handle sparse matrices/lists
def clean_dict(d):
    new_d = {}
    for k, v in d.items():
        if isinstance(v, dict):
            new_d[k] = clean_dict(v)
        elif hasattr(v, 'todense'):  # scipy sparse matrix
            new_d[k] = np.asarray(v.todense())
        else:
            new_d[k] = v
    return new_d

np.savez("SMPLX_NEUTRAL.npz", **clean_dict(data))
print("✅ Converted PKL to NPZ!")
