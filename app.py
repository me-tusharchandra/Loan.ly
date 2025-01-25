import os
import json
import openai
from flask_cors import CORS
from datetime import datetime
from urllib.parse import quote
from twilio.rest import Client
from flask import Flask, request, jsonify, Response
from twilio.twiml.voice_response import VoiceResponse

app = Flask(__name__)
CORS(app)

# Track active calls
active_calls = {}

class Loanly:
    def __init__(self):
        # Credentials setup
        self.twilio_account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
        self.twilio_auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
        self.twilio_phone_number = os.environ.get('TWILIO_PHONE_NUMBER')
        openai.api_key = os.environ.get('OPENAI_API_KEY')

    def generate_loan_questions(self):
        return [
            "What is your current age?",
            "What is your monthly income in Indian Rupees?",
            "Are you a salaried employee, self-employed, or a business owner?",
            "In which city and state do you currently reside?",
            "What is your current occupation and industry?",
            "How much loan amount are you seeking in Indian Rupees?",
            "Do you have a CIBIL credit score?",
            "Are you a first-time loan applicant?",
            "Do you have any existing EMIs or loan commitments?",
            "What is the primary purpose of this loan?"
        ]

    def generate_cc_questions(self):
        return [
            "What is your current age?",
            "What is your annual income in Indian Rupees?",
            "Are you employed in private sector, government, or self-employed?",
            "In which city do you currently work?",
            "Do you have any existing credit cards?",
            "What is your CIBIL credit score?",
            "Have you ever defaulted on any credit or loan payment?",
            "What is your typical monthly household expenditure?",
            "Do you have any existing loan EMIs?",
            "Are you a first-time credit card applicant?"
        ]

financial_system = Loanly()

@app.route('/')
def home():
    return jsonify({
        "message": "Welcome to Loanly, your personal loan and credit card assistant",
        "endpoints": {
            "POST /call-loan": "Initiate a phone call for loan application",
            "POST /call-cc": "Initiate a phone call for credit card application",
            "POST /process-application": "Process a loan/credit card application",
        },
        "status": "running"
    })

@app.route('/call-loan', methods=['POST'])
def call_loan():
    return initiate_automated_call('loan')

@app.route('/call-cc', methods=['POST'])
def call_cc():
    return initiate_automated_call('credit_card')

def initiate_automated_call(application_type):
    try:
        twilio_sid = os.environ.get('TWILIO_ACCOUNT_SID')
        twilio_token = os.environ.get('TWILIO_AUTH_TOKEN')
        twilio_number = os.environ.get('TWILIO_PHONE_NUMBER')
        base_url = os.environ.get('BASE_URL')

        if not all([twilio_sid, twilio_token, twilio_number, base_url]):
            missing = {
                "TWILIO_ACCOUNT_SID": twilio_sid is None,
                "TWILIO_AUTH_TOKEN": twilio_token is None,
                "TWILIO_PHONE_NUMBER": twilio_number is None,
                "BASE_URL": base_url is None
            }
            return jsonify({"error": "Missing required environment variables", "missing": missing}), 400

        data = request.get_json()
        if not data or 'phone_number' not in data:
            return jsonify({"error": "Invalid request data"}), 400

        customer_number = data['phone_number']
        customer_name = data.get('name', 'Customer')

        client = Client(twilio_sid, twilio_token)
        callback_url = f"{base_url}/handle-call?name={quote(customer_name)}&phone_number={quote(customer_number)}"

        call = client.calls.create(
            method='POST',
            url=callback_url,
            to=customer_number,
            from_=twilio_number
        )

        active_calls[customer_number] = {
            'call_sid': call.sid,
            'timestamp': datetime.now()
        }

        return jsonify({"message": "Call initiated", "call_sid": call.sid})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/handle-call', methods=['POST'])
def handle_call():
    response = VoiceResponse()
    
    try:
        # Get the user's speech input if any
        previous_response = request.values.get('SpeechResult')

        if previous_response:
            # Print the response to console
            print(f"User said their name is: {previous_response}")
            # Thank the user and end call
            response.say("Thank you for telling me your name. Goodbye!")
            response.hangup()
        else:
            # Initial greeting and question
            response.say("Hello! This is a test call. Please tell me your name.")
            # Gather speech input
            gather = response.gather(
                input='speech',
                timeout=5,
                action='/handle-call',
                method='POST'
            )

    except Exception as e:
        print(f"Error in handle-call: {str(e)}")
        response.say("An error occurred. Goodbye.")
        response.hangup()

    return Response(str(response), mimetype='text/xml')

@app.route('/debug-env', methods=['GET'])
def debug_env():
    return jsonify({
        "TWILIO_ACCOUNT_SID": os.environ.get('TWILIO_ACCOUNT_SID'),
        "TWILIO_AUTH_TOKEN": os.environ.get('TWILIO_AUTH_TOKEN'),
        "TWILIO_PHONE_NUMBER": os.environ.get('TWILIO_PHONE_NUMBER'),
        "BASE_URL": os.environ.get('BASE_URL'),
        "OPENAI_API_KEY": os.environ.get('OPENAI_API_KEY')
    })

if __name__ == '__main__':
    app.run(port=5000, debug=True)
