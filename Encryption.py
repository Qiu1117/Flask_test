from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes, serialization, padding as symmetric_padding
import os
from flask import (
    Response,
    jsonify,
    request,
    Blueprint,
)
from middleware import token_required, permission_check
import base64
import json
import io


ecryption = Blueprint("ecryption", __name__)


private_key = None

def load_private_key():
    global private_key
    
    if private_key is not None:
        return private_key
    
    try:
        with open(r"RSAKey\CUHK_private_key.pem", "rb") as key_file:
            password = os.environ.get('PRIVATE_KEY_PASSWORD')
            private_key = serialization.load_pem_private_key(
                key_file.read(),
                password=password.encode('utf-8') 
            )
        return private_key
    except Exception as e:
        print(f"加载私钥失败: {str(e)}")
        raise

@ecryption.route("/publickey", methods=["GET"])
@token_required()
def get_public_key():
    """提供RSA公钥给前端用于加密"""
    try:
        with open(r"RSAKey\CUHK_public_key.pem", "rb") as key_file:
            public_key_pem = key_file.read()
        return Response(public_key_pem, mimetype='application/x-pem-file')
    except Exception as e:
        print(f"获取公钥失败: {str(e)}")
        return jsonify({"error": "获取公钥失败", "message": str(e)}), 500


def decrypt_aes_key(encrypted_key, private_key):

    try:
        decrypted_key = private_key.decrypt(
            encrypted_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return decrypted_key
    except Exception as e:
        print(f"解密AES密钥失败: {str(e)}")
        raise

def decrypt_with_aes(encrypted_data, iv, aes_key):
   
    try:
        cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        
        padded_plaintext = decryptor.update(encrypted_data) + decryptor.finalize()
        
        unpadder = symmetric_padding.PKCS7(algorithms.AES.block_size).unpadder()
        plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
        
        return plaintext
    except Exception as e:
        print(f"AES解密失败: {str(e)}")
        raise

def decrypt_file(encrypted_file_content, iv, aes_key):
   
    return decrypt_with_aes(encrypted_file_content, iv, aes_key)

def decrypt_json_data(encrypted_data, iv, aes_key):
    decrypted_data = decrypt_with_aes(encrypted_data, iv, aes_key)
    return json.loads(decrypted_data.decode('utf-8'))

def decrypt_form_data(form_data, private_key):

    encrypted_aes_key = base64.b64decode(form_data.get("encrypted_aes_key", ""))
    aes_key = decrypt_aes_key(encrypted_aes_key, private_key)
    
    result = {"aes_key": aes_key}
    
    if "encrypted_dataset_data" in form_data and "dataset_data_iv" in form_data:
        dataset_data_iv = base64.b64decode(form_data.get("dataset_data_iv"))
        encrypted_dataset_data = base64.b64decode(form_data.get("encrypted_dataset_data"))
        
        decrypted_dataset_data = decrypt_with_aes(encrypted_dataset_data, dataset_data_iv, aes_key)
        result["dataset_data"] = json.loads(decrypted_dataset_data.decode('utf-8'))
    elif "dataset_data" in form_data:
        result["dataset_data"] = json.loads(form_data.get("dataset_data", "{}"))
    
    return result