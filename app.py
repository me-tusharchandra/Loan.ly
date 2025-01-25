import os
import json
import openai
from flask_cors import CORS
from datetime import datetime
from urllib.parse import quote
from twilio.rest import Client
from flask import Flask, request, jsonify, Response
from twilio.twiml.voice_response import VoiceResponse, Say
from twilio.request_validator import RequestValidator
from functools import wraps

app = Flask(__name__)

# Updated CORS configuration
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": [
            "Content-Type",
            "X-Requested-With",
            "X-Twilio-Signature",
            "Authorization"
        ],
        "expose_headers": [
            "Content-Type",
            "X-Twilio-Signature"
        ]
    }
})

# Add security headers middleware
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,X-Twilio-Signature,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    return response

def validate_twilio_request(f):
    """Validates that incoming requests genuinely originated from Twilio"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get the request URL and authentication token
        validator = RequestValidator(os.environ.get('TWILIO_AUTH_TOKEN'))
        
        # Get the original Twilio signature
        twilio_signature = request.headers.get('X-TWILIO-SIGNATURE', '')
        
        # Get the full URL from the request
        url = request.url
        
        # For ngrok URLs, we need to ensure we're using https and the correct host
        if 'ngrok' in url:
            # Get the base URL from environment
            base_url = os.environ.get('BASE_URL', '').rstrip('/')
            if base_url:
                # Reconstruct the URL using the base_url and the path
                url = f"{base_url}{request.path}"
                if request.query_string:
                    url = f"{url}?{request.query_string.decode('utf-8')}"
        
        # Get POST data, handling both form data and JSON
        if request.method == "POST":
            if request.is_json:
                post_data = request.get_json() or {}
            else:
                post_data = request.form.to_dict()
        else:
            post_data = {}
            
        print(f"\n=== Twilio Request Validation ===")
        print(f"Twilio Signature: {twilio_signature}")
        print(f"Request URL: {url}")
        print(f"Post Data: {post_data}")
        print(f"Headers: {dict(request.headers)}")
        print(f"Path: {request.path}")
        print(f"Method: {request.method}")
        print(f"Client IP: {request.remote_addr}")
        
        # Skip validation in development/testing
        if os.environ.get('FLASK_ENV') == 'development':
            print("Skipping validation - development mode")
            return f(*args, **kwargs)
        
        # Validate the request
        is_valid = validator.validate(
            url,
            post_data,
            twilio_signature
        )
        
        print(f"Request validation result: {'Valid' if is_valid else 'Invalid'}")
        
        if is_valid:
            return f(*args, **kwargs)
        
        print("WARNING: Invalid Twilio request signature")
        return Response('Invalid twilio request signature', 403)
        
    return decorated_function

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

    def evaluate_loan_application(self, application_data):
        prompt = f"""
        Loan Application Evaluation for Indian Market:
        Applicant Profile: {json.dumps(application_data, indent=2)}

        Decisioning Criteria:
        1. Age: 18-60 years
        2. Minimum monthly income: ₹25,000
        3. CIBIL Score: Above 600
        4. Loan-to-income ratio: Max 4x annual income

        Provide recommendation:
        - APPROVED
        - REJECTED
        - NEEDS_FURTHER_VERIFICATION
        """

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a loan decisioning expert for Indian applicants."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300
        )
        
        return response.choices[0].message.content.strip()

    def evaluate_cc_application(self, application_data):
        prompt = f"""
        Credit Card Application Evaluation for Indian Market:
        Applicant Profile: {json.dumps(application_data, indent=2)}

        Decisioning Criteria:
        1. Age: 18-60 years
        2. Minimum annual income: ₹3,00,000
        3. CIBIL Score: Above 700
        4. No recent payment defaults
        5. Stable employment

        Provide recommendation:
        - APPROVED
        - REJECTED
        - NEEDS_FURTHER_VERIFICATION
        """

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a credit card decisioning expert for Indian applicants."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300
        )
        
        return response.choices[0].message.content.strip()

    def save_application_result(self, name, phone_number, result, application_type):
        result_data = {
            "name": name,
            "phone_number": phone_number,
            "decision": result,
            "application_type": application_type,
            "timestamp": datetime.now().isoformat()
        }
        
        # Create applications directory if it doesn't exist
        if not os.path.exists('applications'):
            os.makedirs('applications')
            
        # Save to JSON file with timestamp and phone number as identifier
        filename = f"applications/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{phone_number}.json"
        with open(filename, 'w') as f:
            json.dump(result_data, f, indent=2)
        
        return filename

    def send_application_sms(self, customer_name, phone_number, application_type, result):
        try:
            client = Client(
                self.twilio_account_sid,
                self.twilio_auth_token
            )
            
            if result == "APPROVED":
                sms_message = f"Congratulations {customer_name}! Your {application_type} application has been APPROVED. Our team will contact you shortly with next steps."
            elif result == "REJECTED":
                sms_message = f"We regret to inform you that your {application_type} application has been REJECTED at this time. Please try again after 3 months."
            else:
                sms_message = f"Thank you for your {application_type} application. We need some additional verification. Our team will contact you shortly."
            
            print(f"Sending SMS: {sms_message}")
            message = client.messages.create(
                body=sms_message,
                from_=self.twilio_phone_number,
                to=phone_number
            )
            print(f"SMS sent successfully: {message.sid}")
            return True
            
        except Exception as sms_error:
            print(f"Error sending SMS: {str(sms_error)}")
            return False

financial_system = Loanly()

@app.route('/')
def home():
    """Root endpoint for basic connectivity testing"""
    return jsonify({
        "status": "ok",
        "message": "Server is running"
    })

@app.route('/call-loan', methods=['POST'])
def call_loan():
    # Add debug logging
    print("Received call-loan request")
    print("Environment variables status:")
    print(f"TWILIO_ACCOUNT_SID exists: {bool(os.environ.get('TWILIO_ACCOUNT_SID'))}")
    print(f"TWILIO_AUTH_TOKEN exists: {bool(os.environ.get('TWILIO_AUTH_TOKEN'))}")
    print(f"TWILIO_PHONE_NUMBER exists: {bool(os.environ.get('TWILIO_PHONE_NUMBER'))}")
    return initiate_automated_call('loan')

@app.route('/call-cc', methods=['POST'])
def call_cc():
    return initiate_automated_call('credit_card')

def initiate_automated_call(application_type):
    # Get credentials
    twilio_sid = os.environ.get('TWILIO_ACCOUNT_SID')
    twilio_token = os.environ.get('TWILIO_AUTH_TOKEN')
    twilio_number = os.environ.get('TWILIO_PHONE_NUMBER')
    base_url = os.environ.get('BASE_URL', '').rstrip('/')
    
    print("\n=== Call Configuration ===")
    print(f"Application Type: {application_type}")
    print(f"Base URL: {base_url}")
    print(f"Twilio Phone: {twilio_number}")
    print(f"Twilio SID exists: {bool(twilio_sid)}")
    print(f"Twilio Token exists: {bool(twilio_token)}")
    
    # Validate ngrok URL
    if 'ngrok' in base_url:
        try:
            import requests
            # Add more detailed debugging
            print(f"Testing connection to ngrok URL...")
            print(f"Making GET request to: {base_url}/health")
            
            response = requests.get(f"{base_url}/health", timeout=5)
            print(f"Response status code: {response.status_code}")
            print(f"Response body: {response.text}")
            
            if response.status_code != 200:
                print(f"WARNING: Base URL {base_url} returned status code {response.status_code}")
                return jsonify({
                    "error": "Server endpoint not accessible",
                    "details": f"Endpoint returned status {response.status_code}. Please ensure your Flask app is running on port 5001"
                }), 503
        except requests.exceptions.ConnectionError as e:
            print(f"ERROR: Connection failed to {base_url}")
            print(f"Error details: {str(e)}")
            return jsonify({
                "error": "Cannot connect to server",
                "details": "Please ensure both Flask app and ngrok are running correctly"
            }), 503
        except Exception as e:
            print(f"ERROR: Unexpected error connecting to {base_url}: {str(e)}")
            return jsonify({
                "error": "Server endpoint not accessible",
                "details": str(e)
            }), 503

    print(f"Processing {application_type} call request")
    print(f"Using base URL: {base_url}")
    
    if not all([twilio_sid, twilio_token, twilio_number, base_url]):
        missing = {
            "TWILIO_ACCOUNT_SID": twilio_sid is None,
            "TWILIO_AUTH_TOKEN": twilio_token is None,
            "TWILIO_PHONE_NUMBER": twilio_number is None,
            "BASE_URL": base_url is None
        }
        print(f"Missing credentials: {missing}")
        return jsonify({
            "error": "Missing required credentials",
            "missing": missing
        }), 400

    try:
        data = request.get_json()
        print(f"\n=== Request Data ===")
        print(f"Received data: {data}")
        
        customer_number = data.get('phone_number')
        customer_name = data.get('name', 'Customer')
        
        # Check if there's already an active call for this number
        if customer_number in active_calls:
            last_call_time = active_calls[customer_number]['timestamp']
            time_diff = datetime.now() - last_call_time
            
            if time_diff.total_seconds() < 300:
                return jsonify({
                    "error": "Call in progress",
                    "message": "There is already an active call for this number. Please wait for it to complete.",
                    "call_sid": active_calls[customer_number]['call_sid']
                }), 409
            else:
                del active_calls[customer_number]

        print(f"Initiating call to {customer_number} for {customer_name}")
        
        # Construct webhook URL
        callback_url = (
            f"{base_url}/handle-call"
            f"?application_type={quote(application_type)}"
            f"&name={quote(customer_name)}"
            f"&step=0"
            f"&phone_number={quote(customer_number)}"
        )
        
        print(f"\n=== Making Twilio Call ===")
        print(f"To: {customer_number}")
        print(f"From: {twilio_number}")
        print(f"Webhook URL: {callback_url}")
        
        client = Client(twilio_sid, twilio_token)
        call = client.calls.create(
            method='POST',
            url=callback_url,
            to=customer_number,
            from_=twilio_number,
            status_callback=f"{base_url}/call-status",
            status_callback_event=['initiated', 'ringing', 'answered', 'completed'],
            status_callback_method='POST'
        )
        
        print(f"\n=== Call Initiated ===")
        print(f"Call SID: {call.sid}")
        print(f"Status: {call.status}")
        
        # Store call info and return response as before...
        active_calls[customer_number] = {
            'call_sid': call.sid,
            'timestamp': datetime.now(),
            'customer_name': customer_name,
            'application_type': application_type
        }
        
        return jsonify({
            "message": f"Starting {application_type} application call", 
            "call_sid": call.sid,
            "customer": customer_name,
            "phone": customer_number,
            "webhook_url": callback_url
        })
        
    except Exception as e:
        print(f"Error initiating call: {str(e)}")
        return jsonify({
            "error": str(e),
            "type": type(e).__name__
        }), 500

@app.route('/handle-call', methods=['POST', 'GET'])
@validate_twilio_request
def handle_call():
    print("\n=== Starting handle-call ===")
    print(f"Request Method: {request.method}")
    print(f"Request Args: {request.args}")
    print(f"Request Values: {request.values}")
    print(f"Request Headers: {dict(request.headers)}")
    print(f"Request Body: {request.get_data()}")
    
    try:
        # Get parameters from either args or form data
        application_type = request.args.get('application_type') or request.form.get('application_type')
        customer_name = request.args.get('name', 'Customer') or request.form.get('name', 'Customer')
        step = int(request.args.get('step', 0) or request.form.get('step', 0))
        previous_response = request.values.get('SpeechResult', '')
        phone_number = request.args.get('phone_number') or request.form.get('phone_number')
        
        # Set development environment for testing
        os.environ['FLASK_ENV'] = 'development'
        
        print(f"Parameters received:")
        print(f"- Application Type: {application_type}")
        print(f"- Customer Name: {customer_name}")
        print(f"- Step: {step}")
        print(f"- Previous Response: {previous_response}")
        
        # Create a new TwiML response for this request
        twiml_response = VoiceResponse()
        
        # Get appropriate questions based on application type
        questions = (financial_system.generate_loan_questions() if application_type == 'loan' 
                    else financial_system.generate_cc_questions())
        
        # If we're just starting
        if step == 0:
            print("Starting new call flow (step 0)")
            # First just ask if it's a good time to talk
            twiml_response.say(f"Hi {customer_name}, is it the right time to speak to you about your {application_type} application?")
            
            # Create a new gather for this step
            next_url = f"/handle-call?application_type={quote(application_type)}&name={quote(customer_name)}&step=1&phone_number={quote(phone_number if phone_number else '')}"
            gather = twiml_response.gather(
                input='speech',
                action=next_url,
                timeout=5,
                method='POST'
            )
            
        # If it's step 1 (after they've confirmed it's a good time)
        elif step == 1:
            if previous_response and any(word in previous_response.lower() for word in ['yes', 'okay', 'sure', 'go ahead']):
                twiml_response.say(f"Great! I'll ask you a few questions to evaluate your {application_type} application.")
                twiml_response.pause(length=1)
                
                next_url = f"/handle-call?application_type={quote(application_type)}&name={quote(customer_name)}&step=2&phone_number={quote(phone_number if phone_number else '')}"
                gather = twiml_response.gather(
                    input='speech',
                    action=next_url,
                    timeout=5,
                    method='POST'
                )
                gather.say(questions[0])
            else:
                twiml_response.say("I understand this isn't a good time. We'll call you back later. Thank you!")
                twiml_response.hangup()
        
        # If we're in the middle of questions (step 2 onwards)
        elif step < len(questions) + 2:
            print(f"Processing step {step} of {len(questions) + 2}")
            
            # Store previous response if available
            if previous_response:
                print(f"Received response for question {step-2}: {previous_response}")
                session_key = f"{phone_number}_{application_type}"
                if session_key not in active_calls:
                    active_calls[session_key] = {'responses': {}}
                active_calls[session_key]['responses'][step-2] = previous_response
            
            question_index = step - 2  # Adjust for the initial confirmation step
            if question_index < len(questions):
                next_url = f"/handle-call?application_type={quote(application_type)}&name={quote(customer_name)}&step={step+1}&phone_number={quote(phone_number if phone_number else '')}"
                gather = twiml_response.gather(
                    input='speech',
                    action=next_url,
                    timeout=5,
                    method='POST'
                )
                gather.say(questions[question_index])
                print(f"Asked question: {questions[question_index]}")
            else:
                # Process final step
                print("All questions completed, processing final step")
                twiml_response.say("Thank you for providing all the information. I'll now evaluate your application.")
                twiml_response.pause(length=1)
                
                try:
                    # Process application data and send result
                    session_key = f"{phone_number}_{application_type}"
                    application_data = {}
                    if session_key in active_calls and 'responses' in active_calls[session_key]:
                        responses = active_calls[session_key]['responses']
                        for q_index, question in enumerate(questions):
                            if q_index in responses:
                                key = question.rstrip('?').lower().replace(' ', '_')
                                application_data[key] = responses[q_index]
                    
                    # Evaluate application
                    if application_type == 'loan':
                        result = financial_system.evaluate_loan_application(application_data)
                    else:
                        result = financial_system.evaluate_cc_application(application_data)
                    
                    # Save result and send SMS
                    saved_file = financial_system.save_application_result(
                        customer_name,
                        phone_number,
                        result,
                        application_type
                    )
                    
                    # Send SMS
                    financial_system.send_application_sms(customer_name, phone_number, application_type, result)
                    
                    # Complete the call
                    twiml_response.say(f"Based on the information provided, your {application_type} application status is: {result}")
                    twiml_response.say("You will receive an SMS with the detailed result shortly.")
                    twiml_response.say("Thank you for using our service. Goodbye!")
                    twiml_response.hangup()
                    
                except Exception as process_error:
                    print(f"Error in final processing: {str(process_error)}")
                    twiml_response.say("I apologize, but there was an error processing your application. Our team will contact you shortly.")
                    twiml_response.hangup()
        
        # If this is the final step or there's an error, remove from active calls
        if (step >= len(questions) + 2 or 
            'Hangup' in request.values or 
            'CallStatus' in request.values and request.values['CallStatus'] in ['completed', 'failed', 'busy', 'no-answer']):
            if phone_number in active_calls:
                del active_calls[phone_number]
                print(f"Removed {phone_number} from active calls")
        
        # Return the TwiML response with proper headers
        return Response(
            str(twiml_response),
            mimetype='text/xml',
            headers={
                'Content-Type': 'text/xml; charset=utf-8',
                'Cache-Control': 'no-cache'
            }
        )
        
    except Exception as e:
        print(f"Critical error in handle-call: {str(e)}")
        error_response = VoiceResponse()
        error_response.say("I apologize, but there was an error. We will call you back later.")
        error_response.hangup()
        return Response(
            str(error_response),
            mimetype='text/xml',
            headers={
                'Content-Type': 'text/xml; charset=utf-8',
                'Cache-Control': 'no-cache'
            }
        )

@app.route('/process-application', methods=['POST'])
def process_application():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400
        
    name = data.get('name')
    phone_number = data.get('phone_number')
    application_type = data.get('application_type')
    application_data = data.get('application_data')
    
    if not all([name, phone_number, application_type, application_data]):
        return jsonify({"error": "Missing required parameters"}), 400
    
    if application_type not in ['loan', 'credit_card']:
        return jsonify({"error": "Invalid application type"}), 400
    
    try:
        if application_type == 'loan':
            result = financial_system.evaluate_loan_application(application_data)
        else:
            result = financial_system.evaluate_cc_application(application_data)
        
        # Save application result
        saved_file = financial_system.save_application_result(
            name,
            phone_number, 
            result, 
            application_type
        )
        
        return jsonify({
            "result": result,
            "saved_to": saved_file,
            "timestamp": datetime.now().isoformat()
        }) 
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/debug-env', methods=['GET'])
def debug_env():
    return jsonify({
        'twilio_sid_exists': bool(os.environ.get('TWILIO_ACCOUNT_SID')),
        'twilio_token_exists': bool(os.environ.get('TWILIO_AUTH_TOKEN')),
        'twilio_number_exists': bool(os.environ.get('TWILIO_PHONE_NUMBER')),
        'base_url_exists': bool(os.environ.get('BASE_URL')),
        'openai_key_exists': bool(os.environ.get('OPENAI_API_KEY')),
        'base_url': os.environ.get('BASE_URL', 'not set')
    })

@app.route('/call-status', methods=['POST', 'OPTIONS'])
@validate_twilio_request
def call_status():
    # Handle OPTIONS request for CORS
    if request.method == 'OPTIONS':
        response = Response()
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,X-Twilio-Signature,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
        return response

    print("\n=== Call Status Update ===")
    print(f"Status: {request.values.get('CallStatus')}")
    print(f"Call SID: {request.values.get('CallSid')}")
    print(f"All values: {dict(request.values)}")
    print(f"Client IP: {request.remote_addr}")
    
    # For status callbacks, return a simple 200 OK
    return '', 200

@app.route('/health')
def health_check():
    try:
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "base_url": os.environ.get('BASE_URL'),
            "ngrok_url": request.headers.get('X-Forwarded-Proto', 'http') + '://' + request.headers.get('Host', 'unknown'),
            "flask_running": True
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

if __name__ == '__main__':
    # Try different ports if 5001 is in use
    app.run(port=5001, debug=True)