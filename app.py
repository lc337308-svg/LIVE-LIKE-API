# ==============================================================================
#                 MINISTER MULTI-SERVER LIKE, VISIT & AUTO-LIKE API SYSTEM
# ==============================================================================

from flask import Flask, request, jsonify
import asyncio
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from google.protobuf.json_format import MessageToJson
import binascii
import aiohttp
import requests
import json
import like_pb2
import like_count_pb2
import uid_generator_pb2
import time
from collections import defaultdict
from datetime import datetime, timedelta
import random
import os
import urllib.parse
import jwt
from byte import encrypt_api, Encrypt_ID

# --- SECURITY & ACCESS KEYS ---
USER_API_KEY = "Lucky"
ADMIN_KEY = "909090"
KEY_LIMIT = 90

# --- CACHE & TRACKING ---
TOKEN_CACHE = {}
tracker = defaultdict(lambda: [0, time.time()])
liked_cache = defaultdict(set)

app = Flask(__name__)

def get_today_midnight_timestamp():
    now = datetime.now()
    midnight = datetime(now.year, now.month, now.day)
    return midnight.timestamp()

def load_accounts(server_name):
    try:
        if server_name == "IND":
            filename = "account_ind.txt"
        elif server_name in {"BR", "US", "SAC", "NA"}:
            filename = "account_br.txt"
        else:
            filename = "account_bd.txt"

        if not os.path.exists(filename):
            filename = "account_ind.txt"
            if not os.path.exists(filename):
                return []

        accounts = []
        with open(filename, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if ':' in line:
                    parts = line.split(':', 1)
                    uid = parts[0].strip()
                    password = parts[1].strip()
                    if uid and password:
                        accounts.append({"uid": uid, "password": password})
        return accounts
    except Exception:
        return []

def load_tokens(server_name):
    try:
        if server_name == "IND":
            path = "token_ind.json"
        elif server_name in {"BR", "US", "SAC", "NA"}:
            path = "token_br.json"
        else:
            path = "token_bd.json"

        if not os.path.exists(path):
            return []

        with open(path, "r") as f:
            data = json.load(f)

        return [item["token"] for item in data if "token" in item and item["token"] not in ["", "N/A"]]
    except Exception:
        return []

async def generate_jwt_token(uid, password):
    try:
        encoded_password = urllib.parse.quote(password)
        url = f"https://ff-jwt-gen-api.lovable.app/api/public/token?uid={uid}&password={encoded_password}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=24) as response:
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, dict):
                        return data.get('jwt_token') or data.get('token')
                return None
    except Exception:
        return None

async def get_valid_token(uid, password):
    if uid in TOKEN_CACHE:
        cached = TOKEN_CACHE[uid]
        remaining = (cached["expires_at"] - datetime.utcnow()).total_seconds()
        if remaining > 1800:
            return cached["token"]

    token = await generate_jwt_token(uid, password)
    if not token:
        return None

    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        exp = payload.get("exp")
        TOKEN_CACHE[uid] = {"token": token, "expires_at": datetime.utcfromtimestamp(exp)}
    except Exception:
        TOKEN_CACHE[uid] = {"token": token, "expires_at": datetime.utcnow() + timedelta(hours=24)}

    return token

def encrypt_message(plaintext):
    key = b'Yg&tc%DEuh6%Zc^8'
    iv = b'6oyZDr22E3ychjM%'
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded_message = pad(plaintext, AES.block_size)
    return binascii.hexlify(cipher.encrypt(padded_message)).decode('utf-8')

def create_protobuf_message(user_id, region):
    message = like_pb2.like()
    message.uid = int(user_id)
    message.region = region
    return message.SerializeToString()

async def send_like(encrypted_uid, token, url):
    try:
        edata = bytes.fromhex(encrypted_uid)
        headers = {
            'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
            'Authorization': f"Bearer {token}",
            'Content-Type': "application/x-www-form-urlencoded",
            'X-GA': "v1 1",
            'ReleaseVersion': "OB55"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=edata, headers=headers, timeout=5) as response:
                return response.status
    except Exception:
        return 500

async def process_account(target_uid, encrypted_uid, account, url, semaphore, server_name):
    async with semaphore:
        token = await get_valid_token(account['uid'], account['password'])
        if not token:
            return 500, account['uid']

        status = await send_like(encrypted_uid, token, url)
        if status == 200:
            liked_cache[target_uid].add(account['uid'])
        return status, account['uid']

async def send_all_likes(target_uid, server_name, url):
    region = server_name
    protobuf_message = create_protobuf_message(target_uid, region)
    encrypted_uid = encrypt_message(protobuf_message)

    accounts = load_accounts(server_name)
    if not accounts:
        return {'success': 0, 'failed': 0, 'total': 0, 'already_liked': 0}

    already_liked = liked_cache.get(target_uid, set())
    fresh_accounts = [acc for acc in accounts if acc['uid'] not in already_liked]

    if not fresh_accounts:
        return {'success': 0, 'failed': 0, 'total': len(accounts), 'already_liked': len(already_liked)}

    random.shuffle(fresh_accounts)
    semaphore = asyncio.Semaphore(25)
    tasks = [
        process_account(target_uid, encrypted_uid, acc, url, semaphore, server_name)
        for acc in fresh_accounts[:2000]
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    successful = sum(1 for r in results if isinstance(r, tuple) and r[0] == 200)

    return {'success': successful, 'total': len(accounts)}

def enc(uid):
    message = uid_generator_pb2.uid_generator()
    message.krishna_ = int(uid)
    message.teamXdarks = 1
    return encrypt_message(message.SerializeToString())

def decode_protobuf(binary):
    try:
        items = like_count_pb2.Info()
        items.ParseFromString(binary)
        return items
    except Exception:
        return None

def get_player_info(encrypted_uid, server_name, token):
    if server_name == "IND":
        url = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
    elif server_name in {"BR", "US", "SAC", "NA"}:
        url = "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
    else:
        url = "https://clientbp.ggpolarbear.com/GetPlayerPersonalShow"

    edata = bytes.fromhex(encrypted_uid)
    headers = {
        'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
        'Authorization': f"Bearer {token}",
        'Content-Type': "application/x-www-form-urlencoded",
        'X-GA': "v1 1",
        'ReleaseVersion': "OB55"
    }

    try:
        response = requests.post(url, data=edata, headers=headers, verify=False, timeout=10)
        return decode_protobuf(response.content)
    except Exception:
        return None

async def visit_request(session, url, token, data):
    headers = {
        "ReleaseVersion": "OB55",
        "X-GA": "v1 1",
        "Authorization": f"Bearer {token}",
        "Host": url.replace("https://", "").split("/")[0]
    }
    try:
        async with session.post(url, headers=headers, data=data, ssl=False) as resp:
            if resp.status == 200:
                response_data = await resp.read()
                return True, response_data
            return False, None
    except Exception:
        return False, None

async def send_until_2000_success(tokens, uid, server_name, target_success=2000):
    url = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow" if server_name == "IND" else (
        "https://client.us.freefiremobile.com/GetPlayerPersonalShow" if server_name in {"BR", "US", "SAC", "NA"} else
        "https://clientbp.ggpolarbear.com/GetPlayerPersonalShow"
    )
    connector = aiohttp.TCPConnector(limit=0)
    total_success = 0
    total_sent = 0
    player_info = None

    async with aiohttp.ClientSession(connector=connector) as session:
        encrypted = encrypt_api("08" + Encrypt_ID(str(uid)) + "1801")
        data = bytes.fromhex(encrypted)

        while total_success < target_success and total_sent < len(tokens) * 2:
            batch_size = min(target_success - total_success, 100)
            tasks = [
                asyncio.create_task(visit_request(session, url, tokens[(total_sent + i) % len(tokens)], data))
                for i in range(batch_size)
            ]
            results = await asyncio.gather(*tasks)

            for success, response in results:
                if success and response is not None and player_info is None:
                    parsed = decode_protobuf(response)
                    if parsed:
                        try:
                            info_json = json.loads(MessageToJson(parsed))
                            player_info = info_json.get('AccountInfo', {})
                        except Exception:
                            pass

            batch_success = sum(1 for r, _ in results if r)
            total_success += batch_success
            total_sent += batch_size

    return total_success, total_sent, player_info

# ==============================================================================
#                              API ENDPOINTS
# ==============================================================================

@app.route('/like', methods=['GET'])
def handle_like_requests():
    uid = request.args.get("uid")
    server_name = request.args.get("server_name", "").upper()
    key = request.args.get("key")
    client_ip = request.remote_addr

    if key != USER_API_KEY and key != ADMIN_KEY:
        return jsonify({"status": 403, "error": "Unauthorized Access: Invalid or Missing API Key"}), 403

    if not uid or not server_name:
        return jsonify({"status": 400, "error": "Parameters 'uid' and 'server_name' are required"}), 400

    accounts = load_accounts(server_name) or load_accounts("IND")
    if not accounts:
        return jsonify({"status": 500, "error": f"No available accounts for {server_name}"}), 500

    check_token = None
    for account in accounts[:5]:
        check_token = asyncio.run(get_valid_token(account['uid'], account['password']))
        if check_token:
            break

    if not check_token:
        return jsonify({"status": 500, "error": "Authentication Failure"}), 500

    encrypted_uid = enc(uid)

    before = get_player_info(encrypted_uid, server_name, check_token)
    if before is None:
        return jsonify({"status": 404, "error": "Target UID profile not found", "response_code": 0}), 200

    try:
        before_data = json.loads(MessageToJson(before))
        before_like = int(before_data['AccountInfo'].get('Likes', 0))
    except Exception:
        return jsonify({"status": 500, "error": "Protobuf Response Parsing Failure", "response_code": 0}), 200

    like_url = "https://client.ind.freefiremobile.com/LikeProfile" if server_name == "IND" else (
        "https://client.us.freefiremobile.com/LikeProfile" if server_name in {"BR", "US", "SAC", "NA"} else
        "https://clientbp.ggpolarbear.com/LikeProfile"
    )

    asyncio.run(send_all_likes(uid, server_name, like_url))

    after = get_player_info(encrypted_uid, server_name, check_token)
    if after is None:
        return jsonify({"status": 500, "error": "Verification Timeout", "response_code": 0}), 200

    try:
        after_data = json.loads(MessageToJson(after))
        after_like = int(after_data['AccountInfo']['Likes'])
        player_id = int(after_data['AccountInfo']['UID'])
        player_name = str(after_data['AccountInfo']['PlayerNickname'])

        like_given = after_like - before_like
        response_code = 1 if like_given > 0 else 2

        available_likes = len(accounts)
        likes_sent = like_given
        likes_failed = max(available_likes - likes_sent, 0)

        return jsonify({
            "status": "SUCCESS",
            "PlayerNickname": player_name,
            "UID": player_id,
            "LikesbeforeCommand": before_like,
            "LikesafterCommand": after_like,
            "LikesGivenByAPI": like_given,
            "AvailableLikes": available_likes,
            "LikesSent": likes_sent,
            "LikesFailed": likes_failed,
            "remains": "UNLIMITED 👑" if key == ADMIN_KEY else f"({KEY_LIMIT - tracker[client_ip][0]}/{KEY_LIMIT})",
            "response_code": response_code
        })
    except Exception as e:
        return jsonify({"status": 500, "error": str(e)}), 500

@app.route('/visit', methods=['GET'])
def send_visits_route():
    uid = request.args.get("uid")
    server_name = request.args.get("server_name", "IND").upper()
    key = request.args.get("key")

    if key != USER_API_KEY and key != ADMIN_KEY:
        return jsonify({"status": 403, "error": "Invalid API Key"}), 403

    if not uid:
        return jsonify({"status": 400, "error": "UID parameter required"}), 400

    tokens = load_tokens(server_name)
    if not tokens:
        return jsonify({"status": 500, "error": f"No valid tokens found for {server_name}"}), 500

    target_success = 2000
    total_success, total_sent, player_info = asyncio.run(send_until_2000_success(tokens, uid, server_name, target_success))

    return jsonify({
        "status": "SUCCESS",
        "uid": int(uid),
        "success": total_success,
        "fail": max(target_success - total_success, 0),
        "nickname": player_info.get("PlayerNickname", "Unknown") if player_info else "Unknown",
        "region": player_info.get("PlayerRegion", server_name) if player_info else server_name,
        "likes": player_info.get("Likes", 0) if player_info else 0,
        "level": player_info.get("Levels", 0) if player_info else 0
    })

@app.route('/autolike', methods=['GET'])
def handle_auto_like():
    uid = request.args.get("uid")
    server_name = request.args.get("server_name", "IND").upper()
    key = request.args.get("key")
    count_limit = int(request.args.get("count", 5))

    if key != USER_API_KEY and key != ADMIN_KEY:
        return jsonify({"status": 403, "error": "Invalid Key"}), 403

    if not uid:
        return jsonify({"status": 400, "error": "Missing UID"}), 400

    like_url = "https://client.ind.freefiremobile.com/LikeProfile" if server_name == "IND" else (
        "https://client.us.freefiremobile.com/LikeProfile" if server_name in {"BR", "US", "SAC", "NA"} else
        "https://clientbp.ggpolarbear.com/LikeProfile"
    )

    total_given = 0
    rounds_run = 0
    for i in range(count_limit):
        res = asyncio.run(send_all_likes(uid, server_name, like_url))
        given = res.get('success', 0)
        total_given += given
        rounds_run += 1
        if given == 0:
            break
        time.sleep(1)

    return jsonify({
        "status": "SUCCESS",
        "message": f"Auto-like completed for UID {uid}",
        "total_likes_added": total_given,
        "rounds_executed": rounds_run
    })

@app.route('/info', methods=['GET'])
def get_info_bot_data():
    uid = request.args.get("uid")
    server_name = request.args.get("server_name", "").upper()
    key = request.args.get("key")

    if key != USER_API_KEY and key != ADMIN_KEY:
        return jsonify({"status": 403, "error": "Invalid API key"}), 403

    if not uid or not server_name:
        return jsonify({"status": 400, "error": "Missing UID or server_name"}), 400

    accounts = load_accounts(server_name) or load_accounts("IND")
    if not accounts:
        return jsonify({"status": 500, "error": "No available auth accounts"}), 500

    token = None
    for account in accounts[:5]:
        token = asyncio.run(get_valid_token(account['uid'], account['password']))
        if token:
            break

    if not token:
        return jsonify({"status": 500, "error": "Authentication Failure"}), 500

    encrypted_uid = enc(uid)
    info = get_player_info(encrypted_uid, server_name, token)

    if info is None:
        return jsonify({"status": 404, "error": "Player info not found"}), 404

    try:
        info_json = json.loads(MessageToJson(info))
        return jsonify({
            "status": "SUCCESS",
            "data": info_json['AccountInfo']
        })
    except Exception as e:
        return jsonify({"status": 500, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)
