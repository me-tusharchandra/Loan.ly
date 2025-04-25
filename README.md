# [Loan.ly](https://youtu.be/OqbG-eh3_Ns) – click here to save time :))

## Installation

### Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate
```

### Install the requirements

```bash
pip install -r requirements.txt
```

### Start ngrok on the same port as the Flask app

```bash
ngrok http 5001
```

### Update the ngrok URL in `app.py`

```python
BASE_URL = "xyz.ngrok.app"
```

### Run the Flask app

```bash
python app.py
```

## Ideas

No need for an LLM at all – gather the responses and use machine learning to classify the application.

for any other ideas, create an issue on github.
