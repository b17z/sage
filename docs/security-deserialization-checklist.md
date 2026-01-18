# Security Emphasis Update — Senior Engineer Checklist

*Based on the pickle vulnerability catch in Sage v0.2*

---

## The Lesson

```python
# What we had (VULNERABLE)
np.load(embeddings_path, allow_pickle=True)

# What we shipped (SAFE)
np.load(embeddings_path, allow_pickle=False)  # .npy only
json.load(ids_path)                            # IDs separate
```

Pickle files can execute arbitrary code on load. This is a **Remote Code Execution (RCE)** vulnerability. If an attacker can control the pickle file, they own your system.

---

## Add to SENIOR_ENGINEER_CHECKLIST.md

### 🔒 Security Engineer — Enhanced Deserialization Section

**The Serialization Attack Surface:**

```
NEVER trust these with untrusted data:
├── pickle.load()           # Python RCE
├── yaml.load()             # Use yaml.safe_load()
├── eval() / exec()         # Obviously
├── marshal.load()          # Python RCE
├── subprocess with shell=True
├── np.load(allow_pickle=True)
├── torch.load()            # Uses pickle internally
├── joblib.load()           # Uses pickle internally
└── Any "load" that reconstructs objects

SAFE alternatives:
├── JSON                    # Data only, no code
├── numpy .npy              # Arrays only (allow_pickle=False)
├── Protocol Buffers        # Schema-defined
├── MessagePack             # Data only
├── YAML (safe_load only)   # Subset of YAML
└── SQLite / Postgres       # Structured data
```

**The Security Engineer's First Question:**

```
"What can an attacker control?"

If the answer includes ANY of:
├── File contents on disk
├── Network input
├── Database values
├── Environment variables
├── User input (obviously)

Then: NEVER deserialize with pickle/eval/yaml.load
```

**Red Flags in Code Review:**

```python
# 🔴 RED FLAG: pickle with external data
with open(user_provided_path, 'rb') as f:
    data = pickle.load(f)  # RCE if attacker controls file

# 🔴 RED FLAG: torch.load on downloaded models
model = torch.load(downloaded_model_path)  # Pickle under the hood

# 🔴 RED FLAG: yaml.load without safe_load
config = yaml.load(config_file)  # YAML can execute Python

# 🔴 RED FLAG: numpy with pickle
embeddings = np.load(path, allow_pickle=True)  # RCE risk

# 🔴 RED FLAG: joblib with user data
model = joblib.load(user_uploaded_model)  # Pickle under the hood
```

**Safe Patterns:**

```python
# ✅ SAFE: JSON for config/data
config = json.load(config_file)

# ✅ SAFE: yaml.safe_load
config = yaml.safe_load(config_file)

# ✅ SAFE: numpy without pickle
embeddings = np.load(path, allow_pickle=False)

# ✅ SAFE: torch with weights_only (PyTorch 2.0+)
model.load_state_dict(torch.load(path, weights_only=True))

# ✅ SAFE: Explicit schema validation
data = json.load(file)
validated = MySchema.model_validate(data)  # Pydantic
```

---

### Add to Security Engineer Checklist:

```
□ Any pickle/torch/joblib loads?
  └── Can attacker control the file? → VULNERABLE

□ Any yaml.load()?
  └── Is it safe_load()? If not → VULNERABLE

□ Any np.load()?
  └── Is allow_pickle=False? If not → CHECK

□ Any eval()/exec()?
  └── Does input come from user? → VULNERABLE

□ Any subprocess calls?
  └── Is shell=True with user input? → VULNERABLE

□ Model loading (ML projects)?
  └── Using torch.load without weights_only? → CHECK
  └── Using joblib.load on user data? → VULNERABLE
```

---

## Add to ENGINEERING_PRINCIPLES.md — Security Section

### Deserialization: The Silent Killer

```
The Principle:
"Never deserialize untrusted data into objects that can execute code."

The Test:
├── Can an attacker control the serialized data?
├── Does the deserializer execute code? (pickle, yaml, eval)
└── If both yes → you have RCE

The Fix:
├── Use data-only formats (JSON, safe_load, protobuf)
├── Validate schema after loading
├── Sandbox if you MUST deserialize untrusted objects
```

### Dependency Awareness

```
Know what your dependencies do internally:

torch.load()     → uses pickle
joblib.load()    → uses pickle
np.load()        → CAN use pickle (check allow_pickle)
yaml.load()      → CAN execute Python
pandas.read_*()  → Generally safe, but check pickle options
```

---

## Add to Smart Contract Checklist — SENIOR_SC_ENGINEER_CHECKLIST.md

**Note:** Smart contracts don't have pickle, but the principle applies:

```
Never trust external input to control code execution paths:

□ Can calldata control which function executes? (proxy patterns)
□ Can user input become part of a delegatecall target?
□ Can user control the CREATE2 salt in ways that matter?
□ Are there any assembly blocks that use user input as addresses?
```

---

## Quick Reference Card

| Library | Dangerous | Safe |
|---------|-----------|------|
| Python stdlib | `pickle.load()`, `eval()`, `exec()` | `json.load()` |
| PyYAML | `yaml.load()` | `yaml.safe_load()` |
| NumPy | `np.load(allow_pickle=True)` | `np.load(allow_pickle=False)` |
| PyTorch | `torch.load()` | `torch.load(weights_only=True)` |
| Joblib | `joblib.load()` on untrusted | N/A — don't use on untrusted |
| subprocess | `shell=True` + user input | `shell=False`, explicit args |

---

## The Meta-Principle

```
"If it can reconstruct arbitrary objects, it can execute arbitrary code."

Pickle is not a data format. It's a code format.
Treat it like you'd treat eval().
```

---

*Added after Sage v0.2 security review — the paranoia is a feature.*
